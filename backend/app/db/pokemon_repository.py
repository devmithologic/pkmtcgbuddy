"""Acceso a la colección `pokemon`.

1025 documentos diminutos: número, nombre y URL del sprite. Cabe entero en
memoria de MongoDB, así que el buscador responde en microsegundos y puede
dispararse mientras el usuario teclea.
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
    # El número nacional como _id: es una clave natural, única y estable, así que
    # resincronizar es un upsert trivial. Mismo criterio que el id de TCGdex en
    # la colección de cartas.
    #
    # Sin URL: se calcula al leer. Los documentos sincronizados antes conservan
    # su clave `sprite_url` porque replace_all usa $set, que no borra lo que no
    # menciona. Es basura inerte —nadie la lee— y limpiarla no compensa un
    # $unset sobre 1351 documentos.
    return {
        "_id": pokemon.dex_id,
        "name": pokemon.name,
    }


def from_document(document: dict) -> PokemonRefOut:
    return PokemonRefOut(dex_id=document["_id"], name=document["name"])


async def search(query: str, limit: int = 20) -> list[PokemonRefOut]:
    """Busca por nombre, por subcadena y sin distinguir mayúsculas.

    Subcadena y no prefijo por coherencia con el buscador de cartas, y porque los
    nombres de formas regionales llevan el sufijo detrás: buscar «basculegion»
    debe encontrar «basculegion-male».

    re.escape es obligatorio — el texto viene del usuario. Sin él, teclear «(»
    produce una expresión inválida, y patrones como «(a+)+» son un vector de
    denegación de servicio por backtracking catastrófico (ReDoS).
    """
    cursor = (
        _collection()
        .find({"name": {"$regex": re.escape(query.lower())}})
        # Ordenado por número: dentro de una familia evolutiva salen en orden
        # natural, que es como la gente los busca.
        .sort("_id", ASCENDING)
        .limit(limit)
    )
    return [from_document(doc) async for doc in cursor]


async def get_many(dex_ids: list[int]) -> dict[int, PokemonRefOut]:
    """Resuelve varios de una vez. Una consulta, no una por Pokémon."""
    if not dex_ids:
        return {}
    cursor = _collection().find({"_id": {"$in": list(set(dex_ids))}})
    return {doc["_id"]: from_document(doc) async for doc in cursor}


async def count() -> int:
    return await _collection().count_documents({})


async def replace_all(pokemon: list[PokemonRef]) -> int:
    """Escribe el Pokédex entero con upsert.

    Sin lotes: son 1025 documentos de tres campos, un solo bulk_write los cubre.
    Upsert y no borrar-e-insertar, por lo mismo de siempre: borrar deja una
    ventana en la que el buscador no encuentra nada.
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
