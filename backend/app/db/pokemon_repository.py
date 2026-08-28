"""Access to the `pokemon` collection.

1025 tiny documents: number, name and sprite URL. It fits entirely in MongoDB's
memory, so the search responds in microseconds and can fire on every keystroke.
"""

import re

from pymongo import ASCENDING

from app.db.mongo import get_database
from app.models.pokemon import PokemonRef, PokemonRefOut

COLLECTION = "pokemon"


def _collection():
    return get_database()[COLLECTION]


async def ensure_indexes() -> None:
    await _collection().create_index([("name", ASCENDING)])


def to_document(pokemon: PokemonRef) -> dict:
    # The national number as _id: it's a natural key, unique and stable, so
    # resyncing is a trivial upsert. Same criterion as the TCGdex id in the
    # card collection.
    #
    # No URL: it's computed on read. Documents synced before this change keep
    # their `sprite_url` key because replace_all uses $set, which doesn't erase
    # what it doesn't mention. It's inert garbage — nobody reads it — and
    # cleaning it up isn't worth a $unset over 1351 documents.
    return {
        "_id": pokemon.dex_id,
        "name": pokemon.name,
    }


def from_document(document: dict) -> PokemonRefOut:
    return PokemonRefOut(dex_id=document["_id"], name=document["name"])


async def search(query: str, limit: int = 20) -> list[PokemonRefOut]:
    """Searches by name, by substring and case-insensitively.

    Substring and not prefix for consistency with the card search, and because
    regional form names carry the suffix at the end: searching "basculegion"
    must find "basculegion-male".

    re.escape is mandatory — the text comes from the user. Without it, typing
    "(" produces an invalid expression, and patterns like "(a+)+" are a denial
    of service vector via catastrophic backtracking (ReDoS).
    """
    cursor = (
        _collection()
        .find({"name": {"$regex": re.escape(query.lower())}})
        # Sorted by number: within an evolutionary family they come out in
        # natural order, which is how people look for them.
        .sort("_id", ASCENDING)
        .limit(limit)
    )
    return [from_document(doc) async for doc in cursor]


async def get_many(dex_ids: list[int]) -> dict[int, PokemonRefOut]:
    """Resolves several at once. One query, not one per Pokemon."""
    if not dex_ids:
        return {}
    cursor = _collection().find({"_id": {"$in": list(set(dex_ids))}})
    return {doc["_id"]: from_document(doc) async for doc in cursor}


async def count() -> int:
    return await _collection().count_documents({})


async def replace_all(pokemon: list[PokemonRef]) -> int:
    """Writes the whole Pokedex with upsert.

    No batching: it's 1025 documents of three fields, a single bulk_write
    covers them. Upsert and not delete-then-insert, for the usual reason:
    deleting leaves a window in which the search finds nothing.
    """
    from pymongo import UpdateOne

    if not pokemon:
        return 0

    result = await _collection().bulk_write(
        [
            UpdateOne({"_id": p.dex_id}, {"$set": to_document(p)}, upsert=True)
            for p in pokemon
        ],
        ordered=False,
    )
    return result.upserted_count + result.modified_count
