"""TCGdex adapter. The only file in the project that knows its API.

Everything the rest of the code knows is that there are functions that return
`Card` and `CardSearchResult` (see models/card.py). Nobody else sees a TCGdex
URL, one of its field names, or how it paginates.

That is an *adapter*, or an *anti-corruption layer*. The advantage is not
theoretical: if TCGdex shuts down — the way pokemontcg.io did, see CLAUDE.md —
switching providers means rewriting this file, not chasing
`response["legal"]["standard"]` across the whole repository.

We use httpx against the REST API instead of the official SDK. Two reasons: the
SDK hides the HTTP, which here is precisely what needs understanding; and its
own docs publish two card models that are incompatible with each other, so the
API is the more trustworthy of the two sources.
"""

import asyncio
import hashlib
import json

import httpx

from app.models.card import (
    Card,
    CardCategory,
    CardSearchResult,
    CardSummary,
    DeckFormat,
)


class CardSourceError(RuntimeError):
    """TCGdex answered with something we don't know how to interpret.

    Distinct from httpx.HTTPError, which covers transport failures. This one
    covers *content* failures: a 200 with HTML from a downed proxy, a field
    that disappeared, a new category that isn't in our enum.

    It exists because without it those cases would surface as ValueError or
    KeyError, dodge the router's error handling, and end up as a 500 — that is,
    the application would be pleading guilty to someone else's failure.
    Translating the provider's errors is part of the adapter's job, just like
    translating its data.
    """


BASE_URL = "https://api.tcgdex.net/v2/en"

# Concurrent requests against TCGdex. The same number the card sync uses:
# enough that 218 sets take seconds, low enough not to look like an attack on
# a free service that has already gone down once.
CONCURRENCY = 10

# TCGdex marks ACE SPEC as a rarity. This constant is the only appearance of
# the string anywhere in the project; the rest of the code asks is_ace_spec
# instead.
ACE_SPEC_RARITY = "ACE SPEC Rare"

# Telling basic energy apart from special energy turned out not to be
# straightforward, and the first version of this was wrong.
#
# TCGdex has an `energyType` field with values "Normal" and "Special", and it
# looks like the answer. It isn't: it marks Reversal Energy, Prism Energy,
# Team Rocket's Energy, and the nine Scarlet & Violet type-special energies as
# "Normal". Exempting them from the 4-copy limit would allow illegal decks.
#
# The reliable signal is the effect text: a basic energy has none, because it
# does nothing beyond providing energy. Checked against the 316 energies legal
# in Standard: with no effect you get exactly the 8 basic types (under both
# naming conventions, "Fire Energy" and "Basic Fire Energy"), and with an
# effect the 18 special ones. Zero overlap.

# The client is opened in the app's lifespan, same as Mongo's, and for the
# same reason: reusing TCP connections instead of negotiating TLS on every
# search.
_client: httpx.AsyncClient | None = None


async def connect_card_source() -> None:
    global _client
    _client = httpx.AsyncClient(
        base_url=BASE_URL,
        # Without a timeout, a slow TCGdex leaves our requests hanging
        # indefinitely and ends up exhausting the connection pool. It's the
        # most common way a third party's failure becomes your own outage.
        #
        # The deadlines are split apart on purpose, because they cover two
        # situations that don't deserve the same patience:
        #
        #   connect  — establishing TCP + TLS. If the host isn't responding,
        #              it isn't going to: waiting longer doesn't help. 3s and
        #              out.
        #   read     — waiting for the body over a connection already
        #              established. Here it's worth holding on: the server is
        #              working.
        #
        # With a single Timeout(10.0), a downed host made you wait ten seconds
        # to hear what was already known at three.
        timeout=httpx.Timeout(connect=3.0, read=8.0, write=5.0, pool=2.0),
        headers={"User-Agent": "pkmtcgbuddy"},
    )


async def close_card_source() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def _require_client() -> httpx.AsyncClient:
    if _client is None:
        raise RuntimeError("The TCGdex client is not open: did the lifespan run?")
    return _client


def _image_url(base: str | None, quality: str = "low") -> str | None:
    """TCGdex returns the image without an extension: the final URL has to be
    composed.

    'https://assets.tcgdex.net/en/sv/sv03/125' -> '.../125/low.webp'

    A provider detail that must not leak out of this file.
    """
    return f"{base}/{quality}.webp" if base else None


def _parse_list(response: httpx.Response) -> list[dict]:
    """Extracts a list of objects from the body, or fails in a controlled way.

    A 200 does not guarantee JSON: a proxy or CDN in front of TCGdex can
    return an HTML error page with status 200. It's the typical failure mode
    of an unreliable third party, and without this check it shows up as a
    TypeError when trying to iterate the response.
    """
    try:
        payload = response.json()
    except ValueError as exc:  # includes json.JSONDecodeError
        raise CardSourceError("TCGdex returned something that is not JSON") from exc

    if not isinstance(payload, list):
        raise CardSourceError(f"Expected a list, got {type(payload).__name__}")

    return payload


def _to_summary(payload: dict) -> CardSummary:
    try:
        return CardSummary(
            id=payload["id"],
            name=payload["name"],
            image_url=_image_url(payload.get("image")),
        )
    except (KeyError, TypeError) as exc:
        raise CardSourceError(f"Card missing required fields: {exc}") from exc


# Fields that determine WHICH card this is, as opposed to which set it was
# printed in. Deliberately NOT included: set, rarity, illustrator, image,
# variants, regulationMark, or legal. Two printings of Boss's Orders differ in
# all of those and are still the same card.
# `energyType` is NOT included either, even though it looks like it describes
# the card: TCGdex is inconsistent with it. The two printings of Reversal
# Energy have the same text and differ only in that field ('Special' in one,
# 'Normal' in the other), which would split them into two identities when
# they are the same card.
_IDENTITY_FIELDS = (
    "name", "category", "effect", "trainerType",
    "hp", "stage", "evolveFrom", "suffix", "types",
)


def _identity(payload: dict) -> str:
    """The card's fingerprint, identical across all of its reprints.

    It exists because of the reprint rule: if a card gets reprinted in a
    legal set, older printings of the same text become playable too. Boss's
    Orders has printings with regulation marks D, F, G, and I; all six are
    legal because the I-marked one is.

    TCGdex doesn't model that: it marks legality per printing, so its
    G-marked printings come back as illegal. Grouping by this fingerprint is
    what lets us reconstruct the real rule. See card_sync._apply_reprint_rule.

    The name alone isn't enough. Two Pokémon both named "Pikachu" from
    different sets have different attacks: they are different cards, not
    reprints of each other. That's why attacks and abilities are included
    too.
    """
    parts = {k: payload.get(k) for k in _IDENTITY_FIELDS}

    # Attacks and abilities, without the formatting noise.
    parts["attacks"] = [
        {"name": a.get("name"), "cost": a.get("cost"),
         "damage": a.get("damage"), "effect": a.get("effect")}
        for a in (payload.get("attacks") or [])
    ]
    parts["abilities"] = [
        {"name": a.get("name"), "effect": a.get("effect"), "type": a.get("type")}
        for a in (payload.get("abilities") or [])
    ]

    # sort_keys so key order doesn't change the fingerprint; hashed so the
    # full text of every card isn't stored in every document.
    canonical = json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha1(canonical.encode()).hexdigest()[:16]


def _to_card(payload: dict) -> Card:
    """Translates TCGdex's JSON into our model.

    This is where the foreign model stops existing. Note `is_ace_spec`: it
    isn't a copied field, it's a derived rule.
    """
    legal = payload.get("legal") or {}
    rarity = payload.get("rarity")

    try:
        return Card(
            id=payload["id"],
            name=payload["name"],
            image_url=_image_url(payload.get("image")),
            # ValueError if TCGdex adds a category we don't have. That's the
            # risk of translating into a closed enum, and it's preferred over
            # accepting any string: it fails loudly, and in a single place.
            category=CardCategory(payload["category"]),
            rarity=rarity,
            regulation_mark=payload.get("regulationMark"),
            legal_standard=bool(legal.get("standard", False)),
            legal_expanded=bool(legal.get("expanded", False)),
            is_ace_spec=rarity == ACE_SPEC_RARITY,
            is_basic_energy=(
                payload["category"] == CardCategory.ENERGY.value
                and not payload.get("effect")
            ),
            identity=_identity(payload),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise CardSourceError(f"Could not parse the card: {exc}") from exc


async def search_cards(
    name: str | None = None,
    deck_format: DeckFormat | None = None,
    category: CardCategory | None = None,
    ace_spec_only: bool = False,
    page: int = 1,
    page_size: int = 24,
) -> CardSearchResult:
    """Searches cards. Filters are combined with AND.

    The name search is by SUBSTRING and case-insensitive, not by prefix:
    "rod" returns "Aerodactyl" (ae-ROD-actyl). It isn't a bug, it's how TCGdex
    filters, and the UI should say so.
    """
    params: dict[str, str | int] = {
        "pagination:page": page,
        "pagination:itemsPerPage": page_size,
        "sort:field": "name",
        "sort:order": "ASC",
    }

    if name:
        params["name"] = name
    if category:
        params["category"] = category.value
    if ace_spec_only:
        params["rarity"] = ACE_SPEC_RARITY
    if deck_format:
        # 'legal.standard' / 'legal.expanded': the dot is TCGdex's syntax for
        # filtering by a nested field.
        params[f"legal.{deck_format.value}"] = "true"

    response = await _require_client().get("/cards", params=params)
    response.raise_for_status()
    payload = _parse_list(response)

    # TCGdex doesn't return a result total, so "there are more pages" is
    # inferred: if the full page came back, there's probably another one.
    #
    # It's an approximation, and its only failure mode is benign: when the
    # total is an exact multiple of page_size, the last page offers "Next"
    # and the next one comes back empty. We prefer that over the
    # alternative — requesting one extra item — because with page-number
    # pagination `itemsPerPage` also determines the offset: requesting
    # page_size+1 shifts the window and skips a card at every page boundary.
    has_more = len(payload) == page_size

    return CardSearchResult(
        cards=[_to_summary(item) for item in payload],
        page=page,
        page_size=page_size,
        has_more=has_more,
    )


async def get_card(card_id: str) -> Card | None:
    """A card's detail. Returns None if it doesn't exist.

    A separate endpoint is needed because TCGdex's list only carries id, name,
    and image: it filters by fields it doesn't return.

    Consequence worth keeping in mind: showing the rarity for 24 results would
    take 24 extra calls. That's the **N+1** problem — one query for the list
    plus one per item. That's why search shows only name and image, and the
    detail is requested once the user picks a specific card.
    """
    response = await _require_client().get(f"/cards/{card_id}")

    if response.status_code == 404:
        return None
    response.raise_for_status()

    try:
        payload = response.json()
    except ValueError as exc:
        raise CardSourceError("TCGdex returned something that is not JSON") from exc

    return _to_card(payload)


async def fetch_sets() -> list[dict]:
    """Every set, with its OFFICIAL ABBREVIATION and its RELEASE DATE.

    The abbreviation is the piece that makes importing and exporting lists
    possible: the text format used by PTCG Live and the network's tools
    identifies each card as `<abbreviation> <number>` — `MEG 77`, `TEF 129` —
    and that code doesn't appear in TCGdex's id, which is `me01-077`.

    The date is what lets a card's printings be sorted from newest to oldest.
    Without it, Metal Energy's 26 printings came out in id order and the
    first one was from 1999.

    It's TWO passes and not one because the `/sets` list carries neither one
    nor the other: each set has to be requested separately. That's 218
    requests, bounded by the same Semaphore as the card sync so as not to open
    218 connections at once.

    All 218 are saved, not just the 188 that have an abbreviation. The other
    30 — demo decks, old promos — used to be dropped because nobody writes
    them into a list, and that was true for importing. But their cards DO show
    up in search, so they need a date too, and with no document there's
    nowhere to put it. They go in with `abbreviation` set to None, which is
    the truth: they don't have one.
    """
    listing = await _require_client().get("/sets")
    listing.raise_for_status()

    try:
        summaries = listing.json()
    except ValueError as exc:
        raise CardSourceError("TCGdex returned something that is not JSON") from exc

    semaphore = asyncio.Semaphore(CONCURRENCY)
    sets: list[dict] = []

    async def detail(set_id: str) -> None:
        async with semaphore:
            try:
                r = await _require_client().get(f"/sets/{set_id}")
                if r.status_code != 200:
                    return
                d = r.json()
            except (httpx.HTTPError, ValueError):
                # A set that fails must not bring down the whole sync; its
                # absence only means its cards won't be importable by code,
                # and the importer already knows how to report that.
                return

        abbr = (d.get("abbreviation") or {}).get("official")

        sets.append(
            {
                "_id": d["id"],
                "name": d.get("name", ""),
                "abbreviation": abbr.upper() if abbr else None,
                # "YYYY-MM-DD" as-is, without converting to a date: in that
                # format alphabetical order IS chronological order, so Mongo
                # sorts correctly without parsing anything. A set with no
                # date is left as None and sorts last, which is where
                # something undated belongs.
                "release_date": d.get("releaseDate"),
            }
        )

    await asyncio.gather(*(detail(s["id"]) for s in summaries if s.get("id")))
    return sets
