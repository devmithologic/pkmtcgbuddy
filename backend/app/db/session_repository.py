"""Acceso a la colección `sessions`.

Una sola colección: las partidas viven dentro del documento de su sesión. Eso
hace que casi toda operación sea un `update_one` sobre el array `matches`, y que
leer un torneo entero sea una sola lectura.
"""

from datetime import datetime, timezone

from bson import ObjectId
from pymongo import ASCENDING, DESCENDING

from app.db.mongo import get_database
from app.models.match import date_to_bson
from app.models.session import MatchCreate, SessionCreate

COLLECTION = "sessions"


def _collection():
    return get_database()[COLLECTION]


async def ensure_indexes() -> None:
    await _collection().create_index([("played_at", DESCENDING)])
    # La fase 4 agrupará por versión de mazo; el índice ya está listo.
    await _collection().create_index([("deck_version_id", ASCENDING)])


async def create_session(payload: SessionCreate) -> ObjectId:
    now = datetime.now(timezone.utc)
    result = await _collection().insert_one(
        {
            "played_at": date_to_bson(payload.played_at),
            "session_type": payload.session_type.value,
            # ObjectId, no cadena: así el $lookup contra deck_versions funciona
            # sin conversiones y Mongo puede indexarlo.
            "deck_version_id": ObjectId(payload.deck_version_id),
            "name": payload.name,
            "notes": payload.notes,
            "matches": [],
            "created_at": now,
            "updated_at": now,
        }
    )
    return result.inserted_id


async def get_session(session_id: ObjectId) -> dict | None:
    return await _collection().find_one({"_id": session_id})


async def list_sessions() -> list[dict]:
    cursor = _collection().find().sort([("played_at", DESCENDING), ("_id", DESCENDING)])
    return [doc async for doc in cursor]


async def add_match(session_id: ObjectId, match: MatchCreate) -> None:
    """Añade una ronda al final.

    `$push` añade al array sin traérselo primero al servidor de aplicación: la
    operación entera ocurre dentro de MongoDB, así que dos peticiones simultáneas
    no pueden pisarse. Leer el documento, añadir en Python y reescribirlo sería
    el patrón *read-modify-write*, y ahí sí se pierde una de las dos escrituras.

    El número de ronda se calcula como el tamaño actual del array más uno. Con
    `$push` no se puede hacer en la misma operación, así que se lee antes; es un
    número de presentación, no un identificador, y renumerarse al borrar es su
    comportamiento correcto.
    """
    session = await _collection().find_one({"_id": session_id}, {"matches": 1})
    if session is None:
        return

    await _collection().update_one(
        {"_id": session_id},
        {
            "$push": {
                # model_dump y no enumerar los campos a mano. La primera versión
                # los listaba uno a uno, y al añadir los iconos del rival al
                # modelo se guardaron todos menos esos dos: el modelo y la
                # escritura habían quedado desincronizados en silencio.
                #
                # mode="json" convierte los Enum a su valor y los tipos anidados
                # a estructuras que BSON sabe guardar.
                "matches": {
                    "round": len(session["matches"]) + 1,
                    **match.model_dump(mode="json"),
                }
            },
            "$set": {"updated_at": datetime.now(timezone.utc)},
        },
    )


async def update_match(session_id: ObjectId, round_no: int, match: MatchCreate) -> bool:
    """Corrige una ronda. Devuelve False si no existe.

    `matches.$` es el *operador posicional*: actualiza el primer elemento del
    array que cumplió el filtro de la consulta, sin tener que saber su índice.
    """
    # Se reemplaza el elemento entero en vez de campo a campo, por lo mismo:
    # enumerar campos aquí obliga a acordarse de este fichero cada vez que el
    # modelo crece.
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
    """Borra una ronda y renumera las siguientes.

    Renumerar es necesario porque `round` es la posición, no un id: dejar un
    hueco (1, 2, 4) confundiría a quien lea la sesión, y haría que la siguiente
    ronda añadida repitiera un número.

    Son dos operaciones y no hay transacción —MongoDB en modo standalone no las
    soporta—, así que en teoría podría quedar un estado a medias. Se asume: el
    daño sería un array bien formado con la numeración corrida, y volver a
    guardar lo arregla.
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
    """Devuelve {version_id: {"name", "version"}} para un lote de sesiones.

    Dos consultas para toda la lista, pase la que pase. Buscar el mazo de cada
    sesión dentro del bucle serían 2 por sesión: el problema N+1 de
    log_mentor/08, aquí contra nuestra propia base.
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

    return {
        vid: {
            "name": decks.get(v["deck_id"], {}).get("name"),
            "version": v["version"],
        }
        for vid, v in versions.items()
    }
