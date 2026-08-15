"""Acceso a las colecciones `decks` y `deck_versions`.

Dos colecciones referenciadas, no versiones embebidas dentro del mazo. La razón
decisiva es la que viene después: una partida podrá guardar el _id real de la
versión jugada, y agrupar estadísticas por versión será una consulta directa. Con
las versiones embebidas, la partida tendría que apuntar a un subdocumento.

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

from app.db.mongo import get_database, to_object_id  # noqa: F401  (reexportado)
from app.models.card import DeckFormat
from app.models.deck import DeckCard, DeckUpdate, DeckVersionSummary

DECKS = "decks"
VERSIONS = "deck_versions"


def _decks():
    return get_database()[DECKS]


def _versions():
    return get_database()[VERSIONS]


async def ensure_indexes() -> None:
    # Buscar las versiones de un mazo es la consulta más frecuente; el orden
    # descendente sirve para pedir la última sin ordenar en memoria.
    await _versions().create_index([("deck_id", ASCENDING), ("version", DESCENDING)])
    await _decks().create_index([("updated_at", DESCENDING)])


async def update_deck(deck_id: ObjectId, payload: DeckUpdate) -> None:
    """Aplica los cambios enviados y solo esos.

    exclude_unset es la pieza clave de un PATCH: Pydantic distingue entre "el
    cliente no mandó este campo" y "lo mandó a null". Sin ello, un PATCH que solo
    cambia el nombre borraría los iconos, porque llegarían como None por defecto.
    """
    cambios = payload.model_dump(exclude_unset=True)

    # `name` no admite null, por lo mismo que en las sesiones: DeckSummary.name
    # es `str`, así que un nombre nulo hace fallar la validación de la respuesta
    # y GET /api/decks devuelve 500 para todos los mazos, no solo para este.
    # Los dos Pokémon sí: quitarlos es lo que hace la × del selector.
    if "name" in cambios and cambios["name"] is None:
        del cambios["name"]

    # La carpeta es el caso opuesto al nombre: aquí un null SÍ es una orden
    # —«saca el mazo de su carpeta»— así que se conserva, y solo hay que
    # convertirlo a ObjectId cuando trae valor. El texto que llega del cliente no
    # casaría nunca con el _id guardado.
    if "folder_id" in cambios:
        cambios["folder_id"] = (
            ObjectId(cambios["folder_id"]) if cambios["folder_id"] else None
        )

    # El campo de la API se llama `deck_format`; la clave del documento es
    # `format` —así lo escribe create_deck y así lo leen los routers—. Sin este
    # renombrado, el $set crearía un campo `deck_format` que nadie lee: sin
    # error, sin excepción, y el formato sin cambiar. Es el peor tipo de fallo,
    # el que no se queja.
    if "deck_format" in cambios:
        formato = cambios.pop("deck_format")
        if formato is None:
            # Un formato nulo solo puede ser ruido del cliente: un mazo siempre
            # tiene uno. Mismo criterio que `name`.
            pass
        else:
            cambios["format"] = DeckFormat(formato).value

    if not cambios:
        return

    cambios["updated_at"] = datetime.now(timezone.utc)
    await _decks().update_one({"_id": deck_id}, {"$set": cambios})


async def create_deck(
    name: str, deck_format: DeckFormat, folder_id: ObjectId | None = None
) -> str:
    """Crea el mazo y su versión 1, vacía. Devuelve el id del mazo.

    Son dos inserciones y no hay transacción: si la segunda fallara, quedaría un
    mazo sin versión. Se asume porque MongoDB en modo standalone no soporta
    transacciones —requieren un replica set— y el caso es recuperable. En
    producción esto sería un replica set y una transacción.
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
    """Cuántas sesiones se jugaron con alguna versión de este mazo."""
    version_ids = [v["_id"] async for v in _versions().find({"deck_id": deck_id}, {"_id": 1})]
    if not version_ids:
        return 0
    return await get_database()["sessions"].count_documents(
        {"deck_version_id": {"$in": version_ids}}
    )


async def delete_deck(deck_id: ObjectId) -> None:
    """Borra el mazo y todas sus versiones.

    NO comprueba nada: quien decide si se puede borrar es el router, porque la
    respuesta es un 409 con un mensaje, no un dato. Aquí solo se ejecuta.

    Las versiones se borran primero. Al revés quedaría una ventana en la que
    existen versiones cuyo deck_id no apunta a nada, y si el proceso muere en
    medio se quedan así para siempre. Borrar de la hoja hacia la raíz deja como
    peor caso un mazo vacío, que sí se puede volver a borrar.
    """
    await _versions().delete_many({"deck_id": deck_id})
    await _decks().delete_one({"_id": deck_id})


async def get_deck(deck_id: ObjectId) -> dict | None:
    return await _decks().find_one({"_id": deck_id})


async def get_version(version_id: ObjectId) -> dict | None:
    return await _versions().find_one({"_id": version_id})


async def list_decks() -> list[dict]:
    """Mazos con la lista de su versión actual, en una sola pasada.

    Un $lookup es el equivalente en MongoDB a un JOIN. Se usa aquí para no caer
    en el N+1 evidente: pedir los mazos y luego una versión por mazo.
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
        # $lookup siempre devuelve un array; como la referencia es a un único
        # documento, se desenvuelve.
        {"$unwind": {"path": "$current", "preserveNullAndEmptyArrays": True}},
    ]

    # OJO con la asimetría del driver asíncrono, que no perdona:
    #
    #   find(...)          devuelve el cursor directamente, SIN await
    #   await aggregate()  devuelve una corrutina; hay que esperarla para
    #                      obtener el cursor
    #
    # Tratarlas igual da "TypeError: 'async for' requires an object with
    # __aiter__ method, got coroutine", que llega al cliente como un 500.
    cursor = await _decks().aggregate(pipeline)
    return [doc async for doc in cursor]


async def replace_cards(version_id: ObjectId, cards: list[DeckCard]) -> None:
    """Reemplaza la lista de una versión y marca el mazo como modificado."""
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
    """Crea una versión nueva copiando la lista de la actual.

    Copiar es el punto entero del ejercicio: a partir de aquí, la versión
    anterior queda congelada y las partidas ya atribuidas a ella siguen
    describiendo la lista con la que se jugaron de verdad.
    """
    current = await _versions().find_one({"_id": deck["current_version_id"]})
    cards = current["cards"] if current else []

    # El número se calcula desde la versión más alta existente, no desde un
    # contador guardado en el mazo: un contador puede desincronizarse, esto no.
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
    """Historial, de la más reciente a la más antigua."""
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
