"""Access to the `sets` collection.

About 218 documents of four fields: TCGdex id, name, **official abbreviation**
and **release date**.

The abbreviation exists for a single reason, and it's worth stating: the text
format decklists are exchanged in identifies each card by
`<abbreviation> <number>` — `MEG 77` — and the abbreviation is nowhere in the
TCGdex id, which for that same card is `me01-077`. Without it there is no
import or export possible.

The date exists for another: it's the only thing that tells which of the 26
printings of Metal Energy is the current one. Only 188 sets have an
abbreviation, but all 218 have a date and their cards all show up in the
search, so all of them are stored and the abbreviation is allowed to be None.
"""

from pymongo import ASCENDING, UpdateOne
from pymongo.errors import OperationFailure

from app.db.mongo import get_database

COLLECTION = "sets"


def _collection():
    return get_database()[COLLECTION]


async def ensure_indexes() -> None:
    # Unique but PARTIAL. To Mongo, several documents without an abbreviation
    # aren't "several with no value": they're several with the same null value,
    # and a plain unique index would reject the second one. With
    # partialFilterExpression the index only covers documents whose
    # abbreviation is a string, so the 30 sets without a code go in without
    # fighting each other and the 188 with a code still can't be duplicated.
    try:
        await _collection().create_index(
            [("abbreviation", ASCENDING)],
            unique=True,
            partialFilterExpression={"abbreviation": {"$type": "string"}},
        )
    except OperationFailure:
        # The index already exists with the old options — plain unique — and
        # Mongo doesn't rewrite options: it has to be dropped and recreated.
        # This happens once, on the first startup after this change.
        await _collection().drop_index("abbreviation_1")
        await _collection().create_index(
            [("abbreviation", ASCENDING)],
            unique=True,
            partialFilterExpression={"abbreviation": {"$type": "string"}},
        )


async def abbreviation_map() -> dict[str, str]:
    """{ABBREVIATION: set_id}, the whole collection in a dictionary.

    Fetched all at once and resolved in memory for the same reason as folders:
    it's 190 tiny documents, and a decklist has twenty-three lines to
    look up. One query per line would be the N+1 problem over a table that
    fits in an instant.

    Filters by $type string: the 30 sets without an abbreviation would put None
    as the key, and then a decklist line whose code wasn't recognized would
    resolve against the None set instead of being left unresolved.
    """
    cursor = _collection().find({"abbreviation": {"$type": "string"}}, {"abbreviation": 1})
    return {doc["abbreviation"]: doc["_id"] async for doc in cursor}


async def id_map() -> dict[str, str]:
    """The reverse dictionary, {set_id: ABBREVIATION}, for exporting.

    Same filter: a set without an abbreviation is simply not there, and the
    exporter already knows what to do when it can't find a card's code.
    """
    cursor = _collection().find({"abbreviation": {"$type": "string"}}, {"abbreviation": 1})
    return {doc["_id"]: doc["abbreviation"] async for doc in cursor}


async def release_dates() -> dict[str, str]:
    """{set_id: "YYYY-MM-DD"}, so printings can be sorted by age.

    Fetched in full for the same reason as the other two maps: it's 218
    documents of four fields, and whoever uses it — the card backfill — needs
    all of them.
    """
    cursor = _collection().find({"release_date": {"$ne": None}}, {"release_date": 1})
    return {doc["_id"]: doc["release_date"] async for doc in cursor}


async def count() -> int:
    return await _collection().count_documents({})


async def replace_all(sets: list[dict]) -> int:
    """Writes the sets with upsert, same as the Pokedex.

    Upsert and not delete-then-insert: deleting leaves a window in which
    importing a decklist would fail entirely.
    """
    if not sets:
        return 0

    result = await _collection().bulk_write(
        [UpdateOne({"_id": s["_id"]}, {"$set": s}, upsert=True) for s in sets],
        ordered=False,
    )
    return result.upserted_count + result.modified_count
