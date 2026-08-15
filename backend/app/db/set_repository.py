"""Acceso a la colección `sets`.

Unos 190 documentos de tres campos: id de TCGdex, nombre y **abreviatura
oficial**. Existe por una sola razón, y conviene decirla: el formato de texto
con el que se intercambian listas de mazo identifica cada carta por
`<abreviatura> <número>` —`MEG 77`— y la abreviatura no está en ninguna parte
del id de TCGdex, que para esa misma carta es `me01-077`.

Sin esta tabla no hay importación ni exportación posibles.
"""

from pymongo import ASCENDING, UpdateOne

from app.db.mongo import get_database

COLLECTION = "sets"


def _collection():
    return get_database()[COLLECTION]


async def ensure_indexes() -> None:
    await _collection().create_index([("abbreviation", ASCENDING)], unique=True)


async def abbreviation_map() -> dict[str, str]:
    """{ABREVIATURA: set_id}, la colección entera en un diccionario.

    Se trae todo de golpe y se resuelve en memoria por lo mismo que las
    carpetas: son 190 documentos diminutos, y una lista de mazo tiene veintitrés
    líneas que consultar. Una consulta por línea sería el problema N+1 sobre una
    tabla que cabe en un suspiro.
    """
    cursor = _collection().find({}, {"abbreviation": 1})
    return {doc["abbreviation"]: doc["_id"] async for doc in cursor}


async def id_map() -> dict[str, str]:
    """El diccionario inverso, {set_id: ABREVIATURA}, para exportar."""
    cursor = _collection().find({}, {"abbreviation": 1})
    return {doc["_id"]: doc["abbreviation"] async for doc in cursor}


async def count() -> int:
    return await _collection().count_documents({})


async def replace_all(sets: list[dict]) -> int:
    """Escribe los sets con upsert, igual que el Pokédex.

    Upsert y no borrar-e-insertar: borrar deja una ventana en la que importar
    una lista fallaría entera.
    """
    if not sets:
        return 0

    result = await _collection().bulk_write(
        [UpdateOne({"_id": s["_id"]}, {"$set": s}, upsert=True) for s in sets],
        ordered=False,
    )
    return result.upserted_count + result.modified_count
