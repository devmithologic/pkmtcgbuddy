"""Access to MongoDB's `cards` collection.

This module is the local twin of services/card_source.py. One reads from
TCGdex, the other from our own database. Both return the same models —Card,
CardSummary, CardSearchResult— so the router can switch from one to the other
without knowing it.

That symmetry isn't an accident: it's what makes it possible to replace "live
call" with "local query" by changing two lines in the router. When the
adapter was written, that advantage was a promise; here is where it pays off.

The pattern is called *repository*: a layer that encapsulates data access and
exposes domain operations ("find legal cards in Standard") instead of storage
details (filters, indexes, cursors).
"""

from datetime import datetime, timezone

from pymongo import ASCENDING, DESCENDING, UpdateOne

from app.db.mongo import get_database
from app.models.card import (
    Card,
    CardCategory,
    CardSearchResult,
    CardSummary,
    DeckFormat,
)

COLLECTION = "cards"

# The rarity of a plain printing. Basic energies also get reprinted as
# secrets —"Hyper Rare", "Ultra Rare"—, which are the same card with
# decorations.
PLAIN_RARITY = "Common"


def _collection():
    return get_database()[COLLECTION]


def set_id_of(card_id: str) -> str:
    """The id of the set a card belongs to: `me01-077` -> `me01`.

    rpartition and NEVER split: 21 set ids carry hyphens inside them
    (`tk-ex-latia`), so splitting on the first one would return `tk` and the
    card would end up without a date. It's the same trap deck_text.py already
    documents.
    """
    return card_id.rpartition("-")[0]


def sort_name(name: str, is_basic_energy: bool) -> str:
    """The name to sort by, which isn't always the name.

    TCGdex calls the normal basic energy `Metal Energy` and the golden secret
    `Basic Metal Energy`. They're the same card, but sorting by name the
    golden one ALWAYS wins alphabetically, no matter what the date or rarity
    say: "B" comes before "M". Stripping the prefix, the two fall into the
    same group and the tiebreak is decided by `printing_rank`.

    Only for basics. `Basic Research Note` is not the reprint of any
    `Research Note`, and trimming its prefix would send it to the wrong place
    in the list.
    """
    lower_name = name.lower()
    if is_basic_energy and lower_name.startswith("basic "):
        return lower_name.removeprefix("basic ")
    return lower_name


def search_name(name: str, is_basic_energy: bool) -> str:
    """The text the filter searches against, which isn't always the name.

    A basic energy gets "basic" prepended, even if its printing doesn't carry
    it. The reason is that both forms of the name circulate: the current card
    is called `Metal Energy` in TCGdex, but whoever builds a deck searches for
    it — and writes it in a decklist — as *basic Metal Energy*. Without this,
    typing "basic" would only find the eight golden secrets, which are the
    only eight that carry the word in their name.

    Prepending, instead of storing both forms separately, works because the
    search is by substring: "basic metal energy" CONTAINS "metal energy", so a
    single field answers to both ways of writing it.
    """
    if is_basic_energy:
        return f"basic {sort_name(name, True)}"
    return name.lower()


def printing_rank(is_basic_energy: bool, rarity: str | None) -> int:
    """0 for a plain printing, 1 for a secret. Only looks at basics.

    Restricted to basic energies on purpose. On a real card, which of its
    printings goes into the deck is a legitimate decision — the art matters,
    and whoever is looking for `Boss's Orders` wants to see theirs — so
    demoting the special ones would reorder the entire search over a
    preference nobody asked for. On a basic energy there's no decision to
    make: it's the same card with a nicer photo, and what's needed is for the
    plain one to be findable.
    """
    if is_basic_energy and rarity != PLAIN_RARITY:
        return 1
    return 0


async def ensure_indexes() -> None:
    """Creates the indexes the searches need.

    Without an index, every query scans the whole collection (*collection
    scan*). With ~20,000 cards that's milliseconds and goes unnoticed; the
    habit matters all the same, because the day it stops going unnoticed it
    will already be too late.

    create_index is idempotent: if the index exists, it does nothing. That's
    why it can be called on every startup without checking first.
    """
    collection = _collection()
    # Compound, and in EXACTLY the order search_cards sorts by. An index only
    # helps with sorting if its fields and directions match the sort; if they
    # don't, Mongo fetches the documents and sorts them in memory, with a
    # 32 MB cap past which the query fails.
    await collection.create_index(
        [
            ("sort_name", ASCENDING),
            ("printing_rank", ASCENDING),
            ("set_release_date", DESCENDING),
            ("_id", ASCENDING),
        ]
    )
    # The one on identity is used by the image substitution: without it, every
    # results page with a card missing an image would scan the whole
    # collection.
    await collection.create_index([("identity", ASCENDING)])
    await collection.create_index([("category", ASCENDING)])
    await collection.create_index([("legal_standard", ASCENDING)])
    await collection.create_index([("legal_expanded", ASCENDING)])
    await collection.create_index([("is_ace_spec", ASCENDING)])


def card_to_document(card: Card) -> dict:
    """Converts a Card into a storable document.

    Uses the TCGdex id as _id instead of letting Mongo generate an ObjectId.
    It's a *natural key*: it already identifies the card uniquely and stably,
    so reusing it makes resyncing a trivial upsert instead of a lookup by
    another field.
    """
    return {
        "_id": card.id,
        "name": card.name,
        # Derived field, stored on purpose: searching case-insensitively with
        # a case-sensitive regular expression would force Mongo to transform
        # every document at query time, and no index could help. Precomputing
        # is the cheap version.
        "name_lower": card.name.lower(),
        # The two fields used to SORT. Stored precomputed for the same reason
        # as name_lower: deriving them at query time would keep any index from
        # helping, and sorting without an index is sorting in memory.
        "sort_name": sort_name(card.name, card.is_basic_energy),
        "search_name": search_name(card.name, card.is_basic_energy),
        "printing_rank": printing_rank(card.is_basic_energy, card.rarity),
        "image_url": card.image_url,
        "category": card.category.value,
        "rarity": card.rarity,
        "regulation_mark": card.regulation_mark,
        "legal_standard": card.legal_standard,
        "legal_expanded": card.legal_expanded,
        "is_ace_spec": card.is_ace_spec,
        "is_basic_energy": card.is_basic_energy,
        "identity": card.identity,
        "synced_at": datetime.now(timezone.utc),
    }


def card_from_document(document: dict) -> Card:
    return Card(
        id=document["_id"],
        name=document["name"],
        image_url=document.get("image_url"),
        category=CardCategory(document["category"]),
        rarity=document.get("rarity"),
        regulation_mark=document.get("regulation_mark"),
        legal_standard=document["legal_standard"],
        legal_expanded=document["legal_expanded"],
        is_ace_spec=document["is_ace_spec"],
        # .get with a default: documents written before this field existed
        # don't have it. A resync fills them in.
        is_basic_energy=document.get("is_basic_energy", False),
        identity=document.get("identity", ""),
    )


def _build_filter(
    name: str | None,
    deck_format: DeckFormat | None,
    category: CardCategory | None,
    ace_spec_only: bool,
) -> dict:
    """Translates the domain filters into a MongoDB query."""
    # Each basic energy offers ONE printing, not the 27. This lives in the
    # filter and not in the sort because they're different problems: sorting
    # decides which one comes first among the ones that get in, and here what's
    # needed is for the rest to not get in at all. Searching "basic" used to
    # show eight golden collector energies exactly because of this — they were
    # the only eight whose NAME carries the word, and no sort order can rescue
    # a card the filter already threw out.
    #
    # $ne and not False: documents written before the field existed don't have
    # it, and "doesn't have it" means it is offered.
    query: dict = {"is_energy_duplicate": {"$ne": True}}

    if name:
        # Unanchored $regex reproduces TCGdex's behavior: substring, not
        # prefix. "rod" finds "Aerodactyl".
        #
        # re.escape is mandatory: without it, a user who types "(" or "*"
        # triggers an invalid expression, and patterns like "(a+)+" are a
        # denial of service vector via catastrophic backtracking (ReDoS).
        import re

        # Against search_name and not against name_lower: it's the same text
        # except for basic energies, where it carries a leading "basic" that
        # its printing might not have. See search_name().
        query["search_name"] = {"$regex": re.escape(name.lower())}

    if category:
        query["category"] = category.value

    if ace_spec_only:
        query["is_ace_spec"] = True

    if deck_format:
        query[f"legal_{deck_format.value}"] = True

    return query


async def _borrowed_images(documents: list[dict]) -> dict[str, str]:
    """{card_id: url} for cards with no image, borrowed from a reprint.

    TCGdex has no image for 1035 of our 15021 cards, and among them is the
    ENTIRE `sve` set — the 24 current basic energies. Confirmed against its
    API, not inferred: `/cards/sve-008` returns `image: null`, and all 24 do
    the same. It's not a bug on our side and we can't fix it at the source.

    But 566 of those 1035 have a reprint that does have an image, and a
    reprint is THE SAME CARD: same text, same everything except the art. Its
    image gets borrowed.

    Which one gets picked matters: among `sve-008`'s siblings there's a Crown
    Zenith Ultra Rare, and using it would put right back on screen exactly the
    collector's energy this change is trying to remove. That's why it's
    sorted with the same criterion as the search — plain ones first, and among
    those the newest one.

    `identity` is the fingerprint card_source already computes for the reprint
    rule (see card_sync._apply_reprint_rule): the same concept, charged for a
    second time.

    Derived on read and NOT stored. Storing the borrowed URL would mean
    copying into 566 documents a piece of data that belongs to another
    document and that goes stale the moment a new printing comes out — the
    same decision already made for Pokemon sprites, seen from the other side.

    Costs ONE query per page, not one per card: the missing identities are
    gathered and requested together.
    """
    identities = {
        doc["identity"]
        for doc in documents
        if not doc.get("image_url") and doc.get("identity")
    }
    if not identities:
        return {}

    cursor = _collection().find(
        {"identity": {"$in": list(identities)}, "image_url": {"$ne": None}},
        {"identity": 1, "image_url": 1, "printing_rank": 1, "set_release_date": 1},
    )

    best: dict[str, dict] = {}
    async for candidate in cursor:
        current = best.get(candidate["identity"])
        if current is None or _is_better_printing(candidate, current):
            best[candidate["identity"]] = candidate

    return {
        doc["_id"]: best[doc["identity"]]["image_url"]
        for doc in documents
        if not doc.get("image_url") and doc.get("identity") in best
    }


def _is_better_printing(candidate: dict, current: dict) -> bool:
    """Is the candidate "more the card" than the current one?

    Three criteria, the same ones and in the same order the search uses:
    first a plain printing over a secret one, then the newest, and the id to
    break ties. Dates are "YYYY-MM-DD", so comparing them as strings is
    already comparing them as dates.

    Used for two different things that turn out to be the same question:
    which reprint to copy a missing image from, and which of Metal Energy's
    27 printings is the one the search offers.
    """
    rank_candidate = candidate.get("printing_rank", 0)
    rank_current = current.get("printing_rank", 0)
    if rank_candidate != rank_current:
        return rank_candidate < rank_current

    # No date loses: an undated card can't be "the newest".
    date_candidate = candidate.get("set_release_date") or ""
    date_current = current.get("set_release_date") or ""
    if date_candidate != date_current:
        return date_candidate > date_current

    # The id tiebreak isn't cosmetic: without it, which one wins depends on
    # the order Mongo happens to return documents in, and two runs could pick
    # different printings.
    return candidate["_id"] < current["_id"]


def energy_duplicates(documents: list[dict]) -> set[str]:
    """The ids of basic energy printings the search does NOT offer.

    Of the 322 synced basic energy printings, the card selector shows one per
    type: the most recent plain one. The other 313 stay in the database and
    resolve perfectly by id — a deck that already has the SFA golden one in it
    keeps seeing it — but they aren't offered when building.

    Why basic energies and not every card: on a real card, which of its
    printings you put in is a legitimate decision and the art matters, so the
    search shows all of them. On a basic energy there's no decision to make,
    they're the same card, and offering 27 Metal Energy printings isn't
    offering a choice: it's hiding the one that's useful among 26 that add
    nothing.

    Takes ALL the documents and queries nothing, because "the most recent" can
    only be known by looking at the whole set. That is why this calculation
    cannot live in `card_to_document`, which sees one card at a time.
    """
    best: dict[str, dict] = {}
    basics: list[dict] = []

    for doc in documents:
        if not doc.get("is_basic_energy"):
            continue
        basics.append(doc)
        current = best.get(doc["sort_name"])
        if current is None or _is_better_printing(doc, current):
            best[doc["sort_name"]] = doc

    winners = {doc["_id"] for doc in best.values()}
    return {doc["_id"] for doc in basics if doc["_id"] not in winners}


async def search_cards(
    name: str | None = None,
    deck_format: DeckFormat | None = None,
    category: CardCategory | None = None,
    ace_spec_only: bool = False,
    page: int = 1,
    page_size: int = 24,
) -> CardSearchResult:
    """Searches the local collection. Same signature as card_source.search_cards."""
    query = _build_filter(name, deck_format, category, ace_spec_only)

    # skip/limit against our own database does allow the "fetch one extra"
    # trick, because here the offset is explicit and doesn't depend on the
    # limit. This is exactly what couldn't be done against TCGdex's
    # page-number pagination.
    skip = (page - 1) * page_size

    cursor = (
        _collection()
        .find(query, {"name": 1, "image_url": 1, "identity": 1})
        # Four keys, and each one fixes a different problem:
        #
        #   sort_name         groups `Basic Metal Energy` with `Metal Energy`
        #   printing_rank     a basic's secrets, after the plain ones
        #   set_release_date  among plain printings, the newest one wins
        #   _id               final tiebreak, see below
        #
        # The first three are the answer to searching "metal" returning a
        # golden collector energy at the very top and no plain one visible:
        # the golden one won alphabetically and the 26 plain ones came out in
        # id order, so the first was from 1999.
        #
        # The final _id isn't cosmetic.
        #
        # The name is NOT unique: there are dozens of cards named "Pikachu",
        # and among ACE SPECs there are four repeated names. With a sort key
        # that allows ties, MongoDB doesn't guarantee what order it returns
        # the tied documents in, and it can resolve them differently across
        # two runs of the same query — it depends on the plan it picks, which
        # in turn depends on the limit.
        #
        # On a single query it doesn't matter. When paginating with
        # skip/limit it's a bug: each page is an independent query, so a tie
        # that falls right on the boundary can make a card show up on both
        # pages or on neither. Adding _id — unique by definition — makes the
        # order TOTAL and therefore deterministic.
        .sort(
            [
                ("sort_name", ASCENDING),
                ("printing_rank", ASCENDING),
                ("set_release_date", DESCENDING),
                ("_id", ASCENDING),
            ]
        )
        .skip(skip)
        .limit(page_size + 1)
    )

    documents = [doc async for doc in cursor]
    has_more = len(documents) > page_size

    page_items = documents[:page_size]
    borrowed = await _borrowed_images(page_items)

    return CardSearchResult(
        cards=[
            CardSummary(
                id=doc["_id"],
                name=doc["name"],
                image_url=doc.get("image_url") or borrowed.get(doc["_id"]),
            )
            for doc in page_items
        ],
        page=page,
        page_size=page_size,
        has_more=has_more,
    )


async def get_card(card_id: str) -> Card | None:
    """A card's detail. There's no N+1 problem to avoid here: the search
    could return the full document at no extra cost. The split into two
    endpoints is kept for compatibility with what the frontend already
    uses."""
    document = await _collection().find_one({"_id": card_id})
    if not document:
        return None

    card = card_from_document(document)
    if not card.image_url:
        # A card's detail page is where a missing image is most noticeable,
        # and here the extra query only happens when it's actually missing.
        card.image_url = (await _borrowed_images([document])).get(card_id)
    return card


async def get_cards_by_ids(card_ids: list[str]) -> dict[str, Card]:
    """Resolves several cards at once. Returns {card_id: Card}.

    Exists to validate a deck. A deck has up to 60 entries, and the 4-copy
    rule needs each one's name — fetching them one at a time would be 60
    queries: the N+1 problem from log_mentor/08, this time against our own
    database instead of an API.

    `$in` brings them all back in a single query, and the index on _id
    resolves it directly. Returning a dict instead of a list is deliberate:
    whoever is validating needs to look up by id, and a list would force them
    to scan it for every card.

    Ids that don't exist simply don't show up in the result; detecting that is
    deck_rules's job, which raises UNKNOWN_CARD.
    """
    if not card_ids:
        return {}

    # set() removes duplicates: a list can repeat the same id if the client
    # sends two entries of the same card.
    cursor = _collection().find({"_id": {"$in": list(set(card_ids))}})
    documents = [doc async for doc in cursor]

    # The same substitution as in the search, and it's needed here too: this
    # is the query that paints the deck grid, so without it an already-saved
    # energy would keep showing up without an image even though the search
    # shows one for it.
    borrowed = await _borrowed_images(documents)

    cards = {}
    for doc in documents:
        card = card_from_document(doc)
        if not card.image_url:
            card.image_url = borrowed.get(doc["_id"])
        cards[doc["_id"]] = card
    return cards


def _derived(document: dict, dates: dict[str, str]) -> dict:
    """A card's sort fields, computed from what's already stored.

    Exists so both passes of the backfill compute exactly the same thing: the
    first pass needs `sort_name` and `printing_rank` to decide which printing
    of each energy is offered, and the second pass needs them again to write
    them. Duplicating the calculation in both places is how you end up with
    two rules that drift apart.
    """
    basic = document.get("is_basic_energy", False)
    return {
        "_id": document["_id"],
        "is_basic_energy": basic,
        "sort_name": sort_name(document["name"], basic),
        "search_name": search_name(document["name"], basic),
        "printing_rank": printing_rank(basic, document.get("rarity")),
        "set_release_date": dates.get(set_id_of(document["_id"])),
    }


async def restamp_sort_fields(
    dates: dict[str, str], batch_size: int
) -> tuple[int, int]:
    """Recomputes `sort_name`, `printing_rank` and `set_release_date` on every
    card already stored. Returns (written, how many were left without a date).

    Called by the batch job `card_sync.resort()`. Lives here and not there
    because it's an operation over the cards collection from start to finish:
    the only piece that comes from outside is the dictionary of dates, which
    belongs to another collection and is therefore received as an argument
    instead of being queried here.

    Only the three fields needed for the calculation are projected: fetching
    15021 full documents just to read their name would move megabytes for no
    reason.

    There are TWO passes because `is_energy_duplicate` can't be decided card
    by card: to know whether this Metal Energy is the one offered, all 26
    others need to have been seen first. The first pass looks only at basic
    energies —322 documents— and the second one writes.
    """
    collection = _collection()

    basics = [
        _derived(doc, dates)
        async for doc in collection.find(
            {"is_basic_energy": True}, {"name": 1, "rarity": 1, "is_basic_energy": 1}
        )
    ]
    duplicates = energy_duplicates(basics)

    cursor = collection.find({}, {"name": 1, "rarity": 1, "is_basic_energy": 1})

    operations: list[UpdateOne] = []
    written = 0
    without_date = 0

    async for doc in cursor:
        fields = _derived(doc, dates)
        if not fields["set_release_date"]:
            without_date += 1

        operations.append(
            UpdateOne(
                {"_id": doc["_id"]},
                {
                    "$set": {
                        "sort_name": fields["sort_name"],
                        "search_name": fields["search_name"],
                        "printing_rank": fields["printing_rank"],
                        "set_release_date": fields["set_release_date"],
                        "is_energy_duplicate": doc["_id"] in duplicates,
                    }
                },
            )
        )

        # In batches for the same reason as the sync job: one write per card
        # would be 15021 network round trips, and buffering everything to
        # write at the end would mean losing it all if something fails
        # halfway through.
        if len(operations) >= batch_size:
            await collection.bulk_write(operations, ordered=False)
            written += len(operations)
            operations = []

    if operations:
        await collection.bulk_write(operations, ordered=False)
        written += len(operations)

    return written, without_date


async def legality_snapshot() -> list[dict]:
    """The minimum needed from each card to reapply the reprint rule without
    the network.

    Five fields from 15021 documents. The rule needs to see the whole set at
    once — a printing is legal because of what the OTHERS are — so there's no
    way to do it card by card or streaming.
    """
    cursor = _collection().find(
        {},
        {
            "name": 1,
            "category": 1,
            "identity": 1,
            "legal_standard": 1,
            "legal_expanded": 1,
        },
    )
    return [doc async for doc in cursor]


async def save_legality(documents: list[dict], batch_size: int) -> int:
    """Saves `legal_standard` and `legal_expanded` for the documents passed in.

    Receives only the ones that changed, not all 15021: whoever applies the
    rule knows which ones it touched, and writing the rest would just be
    rewriting the value they already had.
    """
    if not documents:
        return 0

    collection = _collection()
    written = 0
    for start in range(0, len(documents), batch_size):
        batch = documents[start : start + batch_size]
        await collection.bulk_write(
            [
                UpdateOne(
                    {"_id": doc["_id"]},
                    {
                        "$set": {
                            "legal_standard": doc["legal_standard"],
                            "legal_expanded": doc["legal_expanded"],
                        }
                    },
                )
                for doc in batch
            ],
            ordered=False,
        )
        written += len(batch)
    return written


async def count_cards() -> int:
    """How many cards are synced. Used to tell "no results" apart from "never
    synced", which are different problems."""
    return await _collection().count_documents({})
