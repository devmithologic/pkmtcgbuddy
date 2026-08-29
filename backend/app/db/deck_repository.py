"""Access to the `decks` and `deck_versions` collections.

Two referenced collections, not versions embedded inside the deck. The
deciding reason is the one that comes next: a game will be able to store the
real _id of the version it was played with, and grouping stats by version will
be a direct query. With embedded versions, the game would have to point at a
subdocument.

    decks                              deck_versions
      _id                                _id
      name                               deck_id  -> decks._id
      format                             version  1, 2, 3…
      current_version_id -> versions     message
      created_at · updated_at            cards    [{card_id, quantity}, …]
                                         created_at
"""

from datetime import datetime, timezone

from bson import ObjectId
from pymongo import ASCENDING, DESCENDING

from app.db.mongo import get_database, to_object_id  # noqa: F401  (re-exported)
from app.models.card import DeckFormat
from app.models.deck import DeckCard, DeckUpdate, DeckVersionSummary

DECKS = "decks"
VERSIONS = "deck_versions"


def _decks():
    return get_database()[DECKS]


def _versions():
    return get_database()[VERSIONS]


async def ensure_indexes() -> None:
    # Looking up a deck's versions is the most frequent query; descending
    # order lets the latest one be requested without sorting in memory.
    await _versions().create_index([("deck_id", ASCENDING), ("version", DESCENDING)])
    await _decks().create_index([("updated_at", DESCENDING)])


async def update_deck(deck_id: ObjectId, payload: DeckUpdate) -> None:
    """Applies the changes sent, and only those.

    exclude_unset is the key piece of a PATCH: Pydantic distinguishes between
    "the client didn't send this field" and "sent it as null". Without it, a
    PATCH that only changes the name would wipe out the icons, because they'd
    arrive as None by default.
    """
    changes = payload.model_dump(exclude_unset=True)

    # `name` doesn't accept null, for the same reason as with sessions:
    # DeckSummary.name is `str`, so a null name fails response validation and
    # GET /api/decks returns 500 for every deck, not just this one. The two
    # Pokemon fields do accept it: clearing them is what the selector's ×
    # does.
    if "name" in changes and changes["name"] is None:
        del changes["name"]

    # The folder is the opposite case from the name: here a null IS an
    # instruction — "take the deck out of its folder" — so it's kept, and only
    # needs converting to ObjectId when it carries a value. The text that
    # arrives from the client would never match the stored _id.
    if "folder_id" in changes:
        changes["folder_id"] = (
            ObjectId(changes["folder_id"]) if changes["folder_id"] else None
        )

    # The API field is called `deck_format`; the document key is `format` —
    # that's what create_deck writes and what the routers read. Without this
    # rename, the $set would create a `deck_format` field that nobody reads: no
    # error, no exception, and the format left unchanged. It's the worst kind
    # of failure, the kind that doesn't complain.
    if "deck_format" in changes:
        format_ = changes.pop("deck_format")
        if format_ is None:
            # A null format can only be client noise: a deck always has one.
            # Same criterion as `name`.
            pass
        else:
            changes["format"] = DeckFormat(format_).value

    if not changes:
        return

    changes["updated_at"] = datetime.now(timezone.utc)
    await _decks().update_one({"_id": deck_id}, {"$set": changes})


async def create_deck(
    name: str, deck_format: DeckFormat, folder_id: ObjectId | None = None
) -> str:
    """Creates the deck and its version 1, empty. Returns the deck's id.

    Two inserts and no transaction: if the second one failed, a deck without a
    version would be left behind. This is accepted because MongoDB in
    standalone mode doesn't support transactions — they require a replica
    set — and the case is recoverable. In production this would be a replica
    set and a transaction.
    """
    now = datetime.now(timezone.utc)

    deck_id = (
        await _decks().insert_one(
            {
                "name": name,
                "format": deck_format.value,
                "folder_id": folder_id,
                "current_version_id": None,
                "created_at": now,
                "updated_at": now,
            }
        )
    ).inserted_id

    version_id = (
        await _versions().insert_one(
            {
                "deck_id": deck_id,
                "version": 1,
                "message": "Lista inicial",
                "cards": [],
                "created_at": now,
            }
        )
    ).inserted_id

    await _decks().update_one(
        {"_id": deck_id}, {"$set": {"current_version_id": version_id}}
    )

    return str(deck_id)


async def sessions_using(deck_id: ObjectId) -> int:
    """How many sessions were played with any version of this deck."""
    version_ids = [v["_id"] async for v in _versions().find({"deck_id": deck_id}, {"_id": 1})]
    if not version_ids:
        return 0
    return await get_database()["sessions"].count_documents(
        {"deck_version_id": {"$in": version_ids}}
    )


async def delete_deck(deck_id: ObjectId) -> None:
    """Deletes the deck and all of its versions.

    Checks NOTHING: whoever decides whether the deletion is allowed is the
    router, because the response is a 409 with a message, not data. Here it
    just executes.

    The versions are deleted first. The other way around would leave a window
    in which versions exist whose deck_id points at nothing, and if the
    process dies in the middle they stay like that forever. Deleting from the
    leaf toward the root leaves, worst case, an empty deck, which can still be
    deleted again.
    """
    await _versions().delete_many({"deck_id": deck_id})
    await _decks().delete_one({"_id": deck_id})


async def get_deck(deck_id: ObjectId) -> dict | None:
    return await _decks().find_one({"_id": deck_id})


async def get_version(version_id: ObjectId) -> dict | None:
    return await _versions().find_one({"_id": version_id})


async def list_decks() -> list[dict]:
    """Decks with their current version's list, in a single pass.

    A $lookup is MongoDB's equivalent of a JOIN. Used here to avoid the
    obvious N+1: fetching the decks and then one version per deck.
    """
    pipeline = [
        {"$sort": {"updated_at": DESCENDING}},
        {
            "$lookup": {
                "from": VERSIONS,
                "localField": "current_version_id",
                "foreignField": "_id",
                "as": "current",
            }
        },
        # $lookup always returns an array; since the reference is to a single
        # document, it's unwrapped.
        {"$unwind": {"path": "$current", "preserveNullAndEmptyArrays": True}},
    ]

    # WATCH OUT for the async driver's asymmetry, which doesn't forgive:
    #
    #   find(...)          returns the cursor directly, WITHOUT await
    #   await aggregate()  returns a coroutine; it must be awaited to get the
    #                      cursor
    #
    # Treating them the same gives "TypeError: 'async for' requires an object
    # with __aiter__ method, got coroutine", which reaches the client as a
    # 500.
    cursor = await _decks().aggregate(pipeline)
    return [doc async for doc in cursor]


async def replace_cards(version_id: ObjectId, cards: list[DeckCard]) -> None:
    """Replaces a version's list and marks the deck as modified."""
    version = await _versions().find_one_and_update(
        {"_id": version_id},
        {"$set": {"cards": [c.model_dump() for c in cards]}},
    )
    if version:
        await _decks().update_one(
            {"_id": version["deck_id"]},
            {"$set": {"updated_at": datetime.now(timezone.utc)}},
        )


async def create_version(deck: dict, message: str) -> str:
    """Creates a new version, copying the current one's list.

    Copying is the entire point of the exercise: from here on, the previous
    version stays frozen and games already attributed to it keep describing
    the list they were actually played with.
    """
    current = await _versions().find_one({"_id": deck["current_version_id"]})
    cards = current["cards"] if current else []

    # The number is computed from the highest existing version, not from a
    # counter stored on the deck: a counter can drift out of sync, this can't.
    last = await _versions().find_one(
        {"deck_id": deck["_id"]}, sort=[("version", DESCENDING)]
    )
    next_number = (last["version"] + 1) if last else 1

    now = datetime.now(timezone.utc)
    version_id = (
        await _versions().insert_one(
            {
                "deck_id": deck["_id"],
                "version": next_number,
                "message": message,
                "cards": cards,
                "created_at": now,
            }
        )
    ).inserted_id

    await _decks().update_one(
        {"_id": deck["_id"]},
        {"$set": {"current_version_id": version_id, "updated_at": now}},
    )

    return str(version_id)


async def list_versions(deck_id: ObjectId) -> list[DeckVersionSummary]:
    """History, from most recent to oldest."""
    cursor = _versions().find({"deck_id": deck_id}).sort("version", DESCENDING)
    return [
        DeckVersionSummary(
            id=str(doc["_id"]),
            version=doc["version"],
            message=doc["message"],
            total_cards=sum(c["quantity"] for c in doc["cards"]),
            created_at=doc["created_at"],
        )
        async for doc in cursor
    ]
