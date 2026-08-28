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
    carpetas = [doc async for doc in _collection().find().sort("name", ASCENDING)]

    cursor = await get_database()[DECKS].aggregate(
        [
            {"$match": {"folder_id": {"$ne": None}}},
            {"$group": {"_id": "$folder_id", "n": {"$sum": 1}}},
        ]
    )
    recuentos = {d["_id"]: d["n"] async for d in cursor}

    for c in carpetas:
        c["deck_count"] = recuentos.get(c["_id"], 0)
    return carpetas


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


async def _mapa_de_padres() -> dict[ObjectId, ObjectId | None]:
    return {d["_id"]: d.get("parent_id") async for d in _collection().find({}, {"parent_id": 1})}


async def crearia_ciclo(folder_id: ObjectId, nuevo_padre: ObjectId | None) -> bool:
    """Would putting `folder_id` inside `nuevo_padre` close a loop?

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
    if nuevo_padre is None:
        return False
    if nuevo_padre == folder_id:
        return True

    padres = await _mapa_de_padres()
    actual = nuevo_padre
    while actual is not None:
        if actual == folder_id:
            return True
        actual = padres.get(actual)
    return False


async def update_folder(folder_id: ObjectId, payload: FolderUpdate) -> None:
    """Renames or moves.

    exclude_unset again, and here it's essential in both directions:
    `parent_id: None` means "to the root" and must be applied, while a
    `name: None` can only be client noise and is dropped.
    """
    cambios = payload.model_dump(exclude_unset=True)

    if "name" in cambios and cambios["name"] is None:
        del cambios["name"]

    if "parent_id" in cambios:
        cambios["parent_id"] = (
            ObjectId(cambios["parent_id"]) if cambios["parent_id"] else None
        )

    if not cambios:
        return

    await _collection().update_one({"_id": folder_id}, {"$set": cambios})


async def delete_folder(folder_id: ObjectId) -> bool:
    """Deletes the folder and MOVES its contents UP to the parent. Never deletes decks.

    This is the part that has to be decided, not the part that codes itself:
    deleting a folder with four decks inside can't take the decks down with it.
    They're inherited upward, which is what a file manager does when you
    ungroup: if the folder was at the root, its children end up at the root.
    """
    carpeta = await _collection().find_one({"_id": folder_id})
    if not carpeta:
        return False

    abuelo = carpeta.get("parent_id")

    await _collection().update_many({"parent_id": folder_id}, {"$set": {"parent_id": abuelo}})
    await get_database()[DECKS].update_many(
        {"folder_id": folder_id}, {"$set": {"folder_id": abuelo}}
    )
    await _collection().delete_one({"_id": folder_id})
    return True
