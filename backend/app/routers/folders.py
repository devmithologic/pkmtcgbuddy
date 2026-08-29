"""Deck folders."""

from bson import ObjectId
from fastapi import APIRouter, HTTPException, status

from app.db import folder_repository
from app.db.mongo import to_object_id
from app.models.folder import FolderCreate, FolderOut, FolderUpdate

router = APIRouter(prefix="/folders", tags=["folders"])


def _to_out(doc: dict) -> FolderOut:
    return FolderOut(
        id=str(doc["_id"]),
        name=doc["name"],
        parent_id=str(doc["parent_id"]) if doc.get("parent_id") else None,
        deck_count=doc.get("deck_count", 0),
    )


async def _exists_or_404(folder_id: ObjectId) -> dict:
    doc = await folder_repository.get_folder(folder_id)
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That folder does not exist")
    return doc


@router.get("", response_model=list[FolderOut])
async def list_folders() -> list[FolderOut]:
    """All folders, flat.

    The client builds the tree from `parent_id`. Returning it already nested
    would require a recursive model and would not save anything: there are ten
    documents, and the frontend needs to be able to walk them by id anyway to
    render the "move to" dropdowns.
    """
    return [_to_out(d) for d in await folder_repository.list_folders()]


@router.post("", response_model=FolderOut, status_code=status.HTTP_201_CREATED)
async def create_folder(payload: FolderCreate) -> FolderOut:
    parent = None
    if payload.parent_id:
        parent = to_object_id(payload.parent_id)
        await _exists_or_404(parent)

    folder_id = await folder_repository.create_folder(payload.name, parent)
    doc = await folder_repository.get_folder(to_object_id(folder_id))
    return _to_out(doc)


@router.patch("/{folder_id}", response_model=FolderOut)
async def update_folder(folder_id: str, payload: FolderUpdate) -> FolderOut:
    oid = to_object_id(folder_id)
    await _exists_or_404(oid)

    # Moving: the cycle must be checked BEFORE writing. If it writes first and
    # checks after, the tree is already broken and has to be undone.
    fields = payload.model_dump(exclude_unset=True)
    if "parent_id" in fields:
        new_parent_id = to_object_id(fields["parent_id"]) if fields["parent_id"] else None
        if new_parent_id is not None:
            await _exists_or_404(new_parent_id)
        if await folder_repository.would_create_cycle(oid, new_parent_id):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "A folder cannot be moved inside itself or one of its subfolders",
            )

    await folder_repository.update_folder(oid, payload)
    return _to_out(await folder_repository.get_folder(oid))


@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_folder(folder_id: str) -> None:
    """Deletes the folder. Its decks and subfolders move up to the parent; they are not deleted."""
    if not await folder_repository.delete_folder(to_object_id(folder_id)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That folder does not exist")
