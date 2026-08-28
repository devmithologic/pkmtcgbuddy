"""Access to the `sessions` collection.

A single collection: games live inside their session's document. That makes
almost every operation an `update_one` on the `matches` array, and reading an
entire tournament is a single read.
"""

from datetime import datetime, timezone

from bson import ObjectId
from pymongo import ASCENDING, DESCENDING

from app.db.mongo import get_database
from app.models.match import date_to_bson
from app.models.session import MatchCreate, SessionCreate, SessionUpdate

COLLECTION = "sessions"


def _collection():
    return get_database()[COLLECTION]


async def ensure_indexes() -> None:
    await _collection().create_index([("played_at", DESCENDING)])
    # Phase 4 will group by deck version; the index is already in place.
    await _collection().create_index([("deck_version_id", ASCENDING)])
    # Index on an array: MongoDB creates one entry per element, so searching
    # {"tags": "gamesmart"} takes advantage of it just like a plain field.
    await _collection().create_index([("tags", ASCENDING)])


async def create_session(payload: SessionCreate) -> ObjectId:
    now = datetime.now(timezone.utc)
    result = await _collection().insert_one(
        {
            "played_at": date_to_bson(payload.played_at),
            "session_type": payload.session_type.value,
            # ObjectId, not a string: this way the $lookup against
            # deck_versions works without conversions and Mongo can index it.
            "deck_version_id": ObjectId(payload.deck_version_id),
            "name": payload.name,
            "notes": payload.notes,
            "tags": payload.tags,
            "matches": [],
            "created_at": now,
            "updated_at": now,
        }
    )
    return result.inserted_id


async def get_session(session_id: ObjectId) -> dict | None:
    return await _collection().find_one({"_id": session_id})


async def list_sessions(tag: str | None = None) -> list[dict]:
    # {"tags": "x"} against an array matches if ANY element equals it. No need
    # for $elemMatch or $in: MongoDB treats equality against an array as
    # "contains". It's the shortcut that makes the filter cheap.
    filtro = {"tags": tag} if tag else {}
    cursor = (
        _collection().find(filtro).sort([("played_at", DESCENDING), ("_id", DESCENDING)])
    )
    return [doc async for doc in cursor]


async def delete_session(session_id: ObjectId) -> bool:
    """Deletes the entire session, with its rounds inside.

    A single operation precisely because the games are embedded: there are no
    orphans to clean up in another collection. It's an advantage of the
    embedded model that isn't visible until it's time to delete.
    """
    result = await _collection().delete_one({"_id": session_id})
    return result.deleted_count > 0


async def list_tags() -> list[dict]:
    """Tags in use, with how many sessions each one has.

    $unwind turns each array element into a document, and $group counts them.
    It's the same technique the stats use with rounds.
    """
    pipeline = [
        {"$match": {"tags": {"$exists": True, "$ne": []}}},
        {"$unwind": "$tags"},
        {"$group": {"_id": "$tags", "sessions": {"$sum": 1}}},
        # Most used first; ties broken alphabetically.
        {"$sort": {"sessions": DESCENDING, "_id": ASCENDING}},
    ]
    cursor = await _collection().aggregate(pipeline)
    return [{"tag": d["_id"], "sessions": d["sessions"]} async for d in cursor]


async def update_session(session_id: ObjectId, payload: SessionUpdate) -> None:
    """Applies only the fields sent.

    Two conversions the dump doesn't do by itself, because the model speaks in
    Python types and the database in BSON:

      played_at        date -> datetime  (BSON has no date without a time)
      deck_version_id  str  -> ObjectId  (so the $lookup keeps working)
    """
    cambios = payload.model_dump(exclude_unset=True)

    # These three don't accept null. SessionUpdate's `T | None` type only
    # exists to express "don't send this"; it's not that the session can be
    # left without a date.
    #
    # Without this pruning, a PATCH with {"played_at": null} writes null, and
    # from there date_from_bson(None) blows up on READ — not just that
    # session, but the entire GET /api/sessions. One bad record brings down
    # the whole list.
    #
    # name, notes and tags DO accept null: clearing them is a legitimate
    # operation.
    for obligatorio in ("played_at", "session_type", "deck_version_id"):
        if obligatorio in cambios and cambios[obligatorio] is None:
            del cambios[obligatorio]

    if not cambios:
        return

    if "played_at" in cambios and cambios["played_at"] is not None:
        cambios["played_at"] = date_to_bson(payload.played_at)
    if "session_type" in cambios and cambios["session_type"] is not None:
        cambios["session_type"] = payload.session_type.value
    if "deck_version_id" in cambios and cambios["deck_version_id"] is not None:
        cambios["deck_version_id"] = ObjectId(payload.deck_version_id)

    cambios["updated_at"] = datetime.now(timezone.utc)
    await _collection().update_one({"_id": session_id}, {"$set": cambios})


async def add_match(session_id: ObjectId, match: MatchCreate) -> None:
    """Appends a round at the end.

    `$push` appends to the array without fetching it to the application server
    first: the whole operation happens inside MongoDB, so two simultaneous
    requests can't step on each other. Reading the document, appending in
    Python and writing it back would be the *read-modify-write* pattern, and
    there one of the two writes does get lost.

    The round number is computed as the array's current size plus one. With
    `$push` that can't be done in the same operation, so it's read
    beforehand; it's a display number, not an identifier, and renumbering on
    delete is its correct behavior.
    """
    session = await _collection().find_one({"_id": session_id}, {"matches": 1})
    if session is None:
        return

    await _collection().update_one(
        {"_id": session_id},
        {
            "$push": {
                # model_dump, not enumerating fields by hand. The first
                # version listed them one by one, and when the opponent's
                # icons were added to the model, everything except those two
                # got saved: the model and the write had silently drifted out
                # of sync.
                #
                # mode="json" converts Enums to their value and nested types
                # to structures BSON knows how to store.
                "matches": {
                    "round": len(session["matches"]) + 1,
                    **match.model_dump(mode="json"),
                }
            },
            "$set": {"updated_at": datetime.now(timezone.utc)},
        },
    )


async def update_match(session_id: ObjectId, round_no: int, match: MatchCreate) -> bool:
    """Corrects a round. Returns False if it doesn't exist.

    `matches.$` is the *positional operator*: it updates the first array
    element that matched the query's filter, without needing to know its
    index.
    """
    # The whole element is replaced instead of field by field, for the same
    # reason: enumerating fields here means having to remember this file every
    # time the model grows.
    result = await _collection().update_one(
        {"_id": session_id, "matches.round": round_no},
        {
            "$set": {
                "matches.$": {"round": round_no, **match.model_dump(mode="json")},
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )
    return result.matched_count > 0


async def delete_match(session_id: ObjectId, round_no: int) -> bool:
    """Deletes a round and renumbers the following ones.

    Renumbering is necessary because `round` is a position, not an id: leaving
    a gap (1, 2, 4) would confuse whoever reads the session, and would make the
    next round added repeat a number.

    Two operations and no transaction — MongoDB in standalone mode doesn't
    support them — so in theory a half-done state could be left behind. This
    is accepted: the damage would be a well-formed array with shifted
    numbering, and saving again fixes it.
    """
    session = await _collection().find_one({"_id": session_id}, {"matches": 1})
    if session is None:
        return False

    restantes = [m for m in session["matches"] if m["round"] != round_no]
    if len(restantes) == len(session["matches"]):
        return False

    for indice, m in enumerate(restantes, start=1):
        m["round"] = indice

    await _collection().update_one(
        {"_id": session_id},
        {"$set": {"matches": restantes, "updated_at": datetime.now(timezone.utc)}},
    )
    return True


async def resolve_decks(sessions: list[dict]) -> dict:
    """Returns {version_id: {"name", "version"}} for a batch of sessions.

    Two queries for the whole list, no matter what. Looking up each session's
    deck inside the loop would be 2 per session: the N+1 problem from
    log_mentor/08, here against our own database.
    """
    version_ids = {s["deck_version_id"] for s in sessions if s.get("deck_version_id")}
    if not version_ids:
        return {}

    db = get_database()
    versions = {
        v["_id"]: v
        async for v in db["deck_versions"].find({"_id": {"$in": list(version_ids)}})
    }
    deck_ids = {v["deck_id"] for v in versions.values()}
    decks = {
        d["_id"]: d async for d in db["decks"].find({"_id": {"$in": list(deck_ids)}})
    }

    # The Pokemon come for free: the deck's document is already here, fetched
    # to get the name. Returning them doesn't add a single query; what used to
    # happen was throwing them away.
    return {
        vid: {
            "name": decks.get(v["deck_id"], {}).get("name"),
            "version": v["version"],
            "primary": decks.get(v["deck_id"], {}).get("primary_pokemon"),
            "secondary": decks.get(v["deck_id"], {}).get("secondary_pokemon"),
        }
        for vid, v in versions.items()
    }
