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
from app.models.session import MatchCreate, SessionCreate, SessionUpdate

COLLECTION = "sessions"


def _collection():
    return get_database()[COLLECTION]


async def ensure_indexes() -> None:
    await _collection().create_index([("played_at", DESCENDING)])
    # La fase 4 agrupará por versión de mazo; el índice ya está listo.
    await _collection().create_index([("deck_version_id", ASCENDING)])
    # Índice sobre un array: MongoDB crea una entrada por elemento, así que
    # buscar {"tags": "gamesmart"} lo aprovecha igual que un campo simple.
    await _collection().create_index([("tags", ASCENDING)])


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
    # {"tags": "x"} sobre un array casa si CUALQUIER elemento vale. No hace falta
    # $elemMatch ni $in: MongoDB trata la igualdad contra un array como
    # "contiene". Es el atajo que hace barato el filtro.
    filtro = {"tags": tag} if tag else {}
    cursor = (
        _collection().find(filtro).sort([("played_at", DESCENDING), ("_id", DESCENDING)])
    )
    return [doc async for doc in cursor]


async def delete_session(session_id: ObjectId) -> bool:
    """Borra la sesión entera, con sus rondas dentro.

    Una sola operación precisamente porque las partidas están embebidas: no hay
    huérfanos que limpiar en otra colección. Es una ventaja del modelo embebido
    que no se ve hasta que toca borrar.
    """
    result = await _collection().delete_one({"_id": session_id})
    return result.deleted_count > 0


async def list_tags() -> list[dict]:
    """Etiquetas en uso, con cuántas sesiones tiene cada una.

    $unwind convierte cada elemento del array en un documento, y $group cuenta.
    Es la misma técnica que usan las estadísticas con las rondas.
    """
    pipeline = [
        {"$match": {"tags": {"$exists": True, "$ne": []}}},
        {"$unwind": "$tags"},
        {"$group": {"_id": "$tags", "sessions": {"$sum": 1}}},
        # Más usadas primero; a igualdad, alfabético.
        {"$sort": {"sessions": DESCENDING, "_id": ASCENDING}},
    ]
    cursor = await _collection().aggregate(pipeline)
    return [{"tag": d["_id"], "sessions": d["sessions"]} async for d in cursor]


async def update_session(session_id: ObjectId, payload: SessionUpdate) -> None:
    """Aplica solo los campos enviados.

    Dos conversiones que el volcado no hace solo, porque el modelo habla en
    tipos de Python y la base en BSON:

      played_at        date -> datetime  (BSON no tiene fecha sin hora)
      deck_version_id  str  -> ObjectId  (para que el $lookup siga funcionando)
    """
    cambios = payload.model_dump(exclude_unset=True)

    # Estos tres no admiten null. El tipo `T | None` de SessionUpdate solo existe
    # para expresar "no lo mandes"; no es que la sesión pueda quedarse sin fecha.
    #
    # Sin esta poda, un PATCH con {"played_at": null} escribe null, y a partir de
    # ahí date_from_bson(None) revienta al LEER — no solo esa sesión, sino
    # GET /api/sessions entero. Un dato malo tumba la lista completa.
    #
    # name, notes y tags sí pueden ser null: vaciarlos es una operación legítima.
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

    # Los Pokémon salen gratis: el documento del mazo ya está aquí, traído para
    # sacar el nombre. Devolverlos no añade ni una consulta; lo que había antes
    # era tirarlos.
    return {
        vid: {
            "name": decks.get(v["deck_id"], {}).get("name"),
            "version": v["version"],
            "primary": decks.get(v["deck_id"], {}).get("primary_pokemon"),
            "secondary": decks.get(v["deck_id"], {}).get("secondary_pokemon"),
        }
        for vid, v in versions.items()
    }
