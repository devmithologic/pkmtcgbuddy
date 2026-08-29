"""PokeAPI adapter. The only file in the project that knows it.

The project's second external provider, and it is contained the same way as
the first: nobody outside this file knows PokeAPI exists, or how a sprite's
URL is built.

It's the same lesson as `card_source.py`, and now it can be verified instead
of just promised: when TCGdex went down on August 9th, switching the whole
application from "live call" to "local lookup" cost two imports, because the
provider was locked inside a single file.

Two differences from the card adapter, both due to the size of the problem:

- No persistent client or pool is needed: it's used once, from the sync job,
  and it's two requests in total.
- There's no remote search. All 1025 Pokémon fit comfortably in Mongo, and the
  search box has to respond while the user is typing.
"""

import httpx

BASE_URL = "https://pokeapi.co/api/v2"

# The images live in PokeAPI's sprite repository, not in its API. They are
# static files served by GitHub's CDN, with a transparent background.
#
# TWO sets are used, because no single one serves both jobs. Measured against
# a sample of 150 of our 1351 ids:
#
#   set                            found        megas   median weight  size
#   sprites/pokemon/                148          63/65     1.2 KB        96×96
#   other/home/                     148          63/65   124.0 KB      512×512
#   other/official-artwork/         147          62/65   125.1 KB      475×475
#   versions/generation-viii/…       81          27/40     0.5 KB        68×56
#
# HOME wins: the exact same coverage as the small sprite — the same two gaps,
# 10159 and 10264, are missing from both — and it includes the megas. The
# official artwork weighs the same and is framed worse. The Sword/Shield box
# icons are ideal in size but lose a third of the megas: they don't exist in
# that set.
ICON_URL = (
    "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{}.png"
)
ART_URL = (
    "https://raw.githubusercontent.com/PokeAPI/sprites/master"
    "/sprites/pokemon/other/home/{}.png"
)

# Every PokeAPI entry, not just the national Pokédex.
#
# The national dex is 1025, but on top of it live 326 more forms: the 97 MEGA
# EVOLUTIONS, the Gigantamax forms, the regional variants, and the alternate
# forms (deoxys-attack, rotom-heat). The megas are needed — the TCG currently
# has Mega Evolution sets — and the rest don't get in the way: they're
# three-field documents.
#
# A generous limit is requested instead of the exact count, to avoid chaining
# two requests. PokeAPI returns whatever there is.
FETCH_LIMIT = 3000


class PokemonSourceError(RuntimeError):
    """PokeAPI answered with something we don't know how to interpret.

    Same as CardSourceError: translating the provider's errors is part of the
    adapter's job, not just translating its data.
    """


def icon_url(dex_id: int) -> str:
    """The lightweight sprite, for places with many at once.

    Search's 20 results and a session's five rounds. At 1.2 KB, a whole
    search costs 24 KB; with the renders it would cost 2.5 MB.
    """
    return ICON_URL.format(dex_id)


def art_url(dex_id: int) -> str:
    """The Pokémon HOME render, for places where the image *is* the heading.

    The deck's own page and the deck list: few images, and big ones.
    """
    return ART_URL.format(dex_id)


def _id_from_url(url: str) -> int:
    """Pulls the id out of the resource URL: .../pokemon/10033/ -> 10033.

    This is needed because the id can NOT be inferred from the position in
    the list. The first version of this file used enumerate(), and it worked
    by accident: from 1 to 1025 the index happens to match the national
    number. The megas start at 10033, so as soon as the full list was
    requested the assumption broke and every one of them would have ended up
    with the wrong id.

    It's the kind of assumption you only see fail when the data changes, not
    when the code does.
    """
    return int(url.rstrip("/").rsplit("/", 1)[-1])


async def fetch_all() -> list[dict]:
    """Downloads every entry: national, megas, Gigantamax, and forms.

    A single request. Requesting each one's detail would be 1351 calls: the
    N+1 problem from log_mentor/08 in its most literal form.

    Returns plain dicts — {dex_id, name} — and not PokemonRef objects, and
    that's deliberate: `models/pokemon.py` needs to import icon_url and
    art_url from here to compute them on read. If this file also imported
    PokemonRef, the two modules would import each other and Python would fail
    to start with an ImportError. With the import removed from this side, the
    dependency stays one-directional — model → adapter — and the one who
    builds the PokemonRef objects is pokemon_sync, which already imports
    both.
    """
    async with httpx.AsyncClient(
        base_url=BASE_URL,
        timeout=httpx.Timeout(connect=3.0, read=20.0, write=5.0, pool=2.0),
        headers={"User-Agent": "pkmtcgbuddy"},
    ) as client:
        response = await client.get("/pokemon", params={"limit": FETCH_LIMIT, "offset": 0})
        response.raise_for_status()

        try:
            payload = response.json()
            results = payload["results"]
        except (ValueError, KeyError, TypeError) as exc:
            raise PokemonSourceError(f"Unexpected response from PokeAPI: {exc}") from exc

    references = []
    for entry in results:
        try:
            ident = _id_from_url(entry["url"])
        except (KeyError, ValueError):
            # An entry with an odd URL must not bring down the whole sync.
            continue
        references.append({"dex_id": ident, "name": entry["name"]})
    return references
