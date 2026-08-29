"""Access to the `folders` collection.

    folders                      decks
      _id                          _id
      name                         folder_id  -> folders._id  (or null)
      parent_id -> folders._id     …
      created_at

A handful of documents with three fields. Every operation fetches the whole
collection, and that's not carelessness: it's what allows using the simplest
possible tree model. See the docstring in models/folder.py.
"""

from datetime import datetime, timezone

from bson import ObjectId
from pymongo import ASCENDING

from app.db.mongo import get_database
from app.models.folder import FolderUpdate

COLLECTION = "folders"
DECKS = "decks"


def _collection():
    return get_database()[COLLECTION]


async def ensure_indexes() -> None:
    await _collection().create_index([("parent_id", ASCENDING)])
    # Decks are filtered by folder when grouping the listing.
    await get_database()[DECKS].create_index([("folder_id", ASCENDING)])


async def list_folders() -> list[dict]:
    """All folders, with how many decks hang directly off each one.

    Two queries for the whole tree, no matter what. The count comes from an
    aggregation over `decks` and not from counting inside a loop: that would be
    one query per folder, the usual N+1.
    """
    folders = [doc async for doc in _collection().find().sort("name", ASCENDING)]

    cursor = await get_database()[DECKS].aggregate(
        [
            {"$match": {"folder_id": {"$ne": None}}},
            {"$group": {"_id": "$folder_id", "n": {"$sum": 1}}},
        ]
    )
    counts = {d["_id"]: d["n"] async for d in cursor}

    for c in folders:
        c["deck_count"] = counts.get(c["_id"], 0)
    return folders


async def get_folder(folder_id: ObjectId) -> dict | None:
    return await _collection().find_one({"_id": folder_id})


async def create_folder(name: str, parent_id: ObjectId | None) -> str:
    result = await _collection().insert_one(
        {
            "name": name,
            "parent_id": parent_id,
            "created_at": datetime.now(timezone.utc),
        }
    )
    return str(result.inserted_id)


async def _parent_map() -> dict[ObjectId, ObjectId | None]:
    return {d["_id"]: d.get("parent_id") async for d in _collection().find({}, {"parent_id": 1})}


async def would_create_cycle(folder_id: ObjectId, new_parent: ObjectId | None) -> bool:
    """Would putting `folder_id` inside `new_parent` close a loop?

    This is the check that distinguishes a tree from a graph, and without it
    the structure silently corrupts: dragging "Competitive" inside its own
    child "Standard" leaves both of them outside the tree — neither hangs from
    the root anymore — so they vanish from the listing without being deleted,
    and walking the cycle to render them hangs the browser.

    Solved by climbing from the proposed parent toward the root: if the
    folder itself shows up along the way, the branch would close on itself. It
    always terminates, because the existing tree has no cycles and each step
    climbs one level.
    """
    if new_parent is None:
        return False
    if new_parent == folder_id:
        return True

    parents = await _parent_map()
    current = new_parent
    while current is not None:
        if current == folder_id:
            return True
        current = parents.get(current)
    return False


async def update_folder(folder_id: ObjectId, payload: FolderUpdate) -> None:
    """Renames or moves.

    exclude_unset again, and here it's essential in both directions:
    `parent_id: None` means "to the root" and must be applied, while a
    `name: None` can only be client noise and is dropped.
    """
    changes = payload.model_dump(exclude_unset=True)

    if "name" in changes and changes["name"] is None:
        del changes["name"]

    if "parent_id" in changes:
        changes["parent_id"] = (
            ObjectId(changes["parent_id"]) if changes["parent_id"] else None
        )

    if not changes:
        return

    await _collection().update_one({"_id": folder_id}, {"$set": changes})


async def delete_folder(folder_id: ObjectId) -> bool:
    """Deletes the folder and MOVES its contents UP to the parent. Never deletes decks.

    This is the part that has to be decided, not the part that codes itself:
    deleting a folder with four decks inside can't take the decks down with it.
    They're inherited upward, which is what a file manager does when you
    ungroup: if the folder was at the root, its children end up at the root.
    """
    folder = await _collection().find_one({"_id": folder_id})
    if not folder:
        return False

    grandparent = folder.get("parent_id")

    await _collection().update_many({"parent_id": folder_id}, {"$set": {"parent_id": grandparent}})
    await get_database()[DECKS].update_many(
        {"folder_id": folder_id}, {"$set": {"folder_id": grandparent}}
    )
    await _collection().delete_one({"_id": folder_id})
    return True
