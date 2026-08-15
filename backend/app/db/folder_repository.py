"""Acceso a la colección `folders`.

    folders                      decks
      _id                          _id
      name                         folder_id  -> folders._id  (o null)
      parent_id -> folders._id     …
      created_at

Una decena de documentos de tres campos. Todas las operaciones se traen la
colección entera, y eso no es descuido: es lo que permite usar el modelo de árbol
más simple. Ver el docstring de models/folder.py.
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
    # Los mazos se filtran por carpeta al agrupar el listado.
    await get_database()[DECKS].create_index([("folder_id", ASCENDING)])


async def list_folders() -> list[dict]:
    """Todas las carpetas, con cuántos mazos cuelgan directamente de cada una.

    Dos consultas para el árbol entero, pase el que pase. El recuento sale de una
    agregación sobre `decks` y no de contar dentro del bucle: eso último sería
    una consulta por carpeta, el N+1 de siempre.
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
    """¿Meter `folder_id` dentro de `nuevo_padre` cerraría un bucle?

    Es la comprobación que distingue un árbol de un grafo, y sin ella la
    estructura se corrompe en silencio: arrastrar «Competitivo» dentro de su
    propia hija «Standard» deja a las dos fuera del árbol —ninguna cuelga ya de
    la raíz— así que desaparecen del listado sin borrarse, y recorrer el ciclo
    para pintarlas cuelga el navegador.

    Se resuelve subiendo desde el padre propuesto hacia la raíz: si por el camino
    aparece la propia carpeta, la rama se cerraría sobre sí misma. Termina
    siempre, porque el árbol ya existente no tiene ciclos y cada paso sube uno.
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
    """Renombra o mueve.

    exclude_unset otra vez, y aquí es imprescindible en los dos sentidos:
    `parent_id: None` significa «a la raíz» y hay que aplicarlo, mientras que un
    `name: None` solo puede ser basura y se descarta.
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
    """Borra la carpeta y SUBE su contenido al padre. Nunca borra mazos.

    Es la parte que hay que decidir, no la que se programa sola: borrar una
    carpeta con cuatro mazos dentro no puede llevarse los mazos por delante. Se
    heredan hacia arriba, que es lo que hace un gestor de archivos cuando
    desagrupas: si la carpeta estaba en la raíz, sus hijos acaban en la raíz.
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
