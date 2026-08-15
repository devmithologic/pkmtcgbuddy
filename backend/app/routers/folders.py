"""Carpetas de mazos."""

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


async def _existe_o_404(folder_id: ObjectId) -> dict:
    doc = await folder_repository.get_folder(folder_id)
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Esa carpeta no existe")
    return doc


@router.get("", response_model=list[FolderOut])
async def list_folders() -> list[FolderOut]:
    """Todas las carpetas, planas.

    El árbol lo arma el cliente a partir de `parent_id`. Devolverlo ya anidado
    obligaría a un modelo recursivo y no ahorraría nada: son diez documentos, y
    el frontend necesita de todos modos poder recorrerlos por id para pintar los
    desplegables de «mover a».
    """
    return [_to_out(d) for d in await folder_repository.list_folders()]


@router.post("", response_model=FolderOut, status_code=status.HTTP_201_CREATED)
async def create_folder(payload: FolderCreate) -> FolderOut:
    parent = None
    if payload.parent_id:
        parent = to_object_id(payload.parent_id)
        await _existe_o_404(parent)

    folder_id = await folder_repository.create_folder(payload.name, parent)
    doc = await folder_repository.get_folder(to_object_id(folder_id))
    return _to_out(doc)


@router.patch("/{folder_id}", response_model=FolderOut)
async def update_folder(folder_id: str, payload: FolderUpdate) -> FolderOut:
    oid = to_object_id(folder_id)
    await _existe_o_404(oid)

    # Mover: hay que comprobar el ciclo ANTES de escribir. Si se escribe primero
    # y se comprueba después, el árbol ya está roto y hace falta deshacerlo.
    campos = payload.model_dump(exclude_unset=True)
    if "parent_id" in campos:
        nuevo = to_object_id(campos["parent_id"]) if campos["parent_id"] else None
        if nuevo is not None:
            await _existe_o_404(nuevo)
        if await folder_repository.crearia_ciclo(oid, nuevo):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Una carpeta no puede moverse dentro de sí misma ni de una de sus subcarpetas",
            )

    await folder_repository.update_folder(oid, payload)
    return _to_out(await folder_repository.get_folder(oid))


@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_folder(folder_id: str) -> None:
    """Borra la carpeta. Sus mazos y subcarpetas suben al padre, no se borran."""
    if not await folder_repository.delete_folder(to_object_id(folder_id)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Esa carpeta no existe")
