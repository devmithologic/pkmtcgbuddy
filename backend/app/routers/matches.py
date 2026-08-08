"""Endpoints del recurso /api/matches."""

from fastapi import APIRouter, status

from app.db.mongo import get_database
from app.models.match import (
    MatchCreate,
    MatchOut,
    match_from_document,
    match_to_document,
)

# Un APIRouter agrupa las rutas de un recurso. main.py lo monta con el prefijo
# /api, así que las rutas de aquí acaban en /api/matches. El tag agrupa el recurso
# en la documentación automática de /docs.
router = APIRouter(prefix="/matches", tags=["matches"])

COLLECTION = "matches"


@router.post("", response_model=MatchOut, status_code=status.HTTP_201_CREATED)
async def create_match(match: MatchCreate) -> MatchOut:
    """Registra una partida.

    El parámetro anotado con MatchCreate es lo que hace el trabajo: FastAPI lee el
    cuerpo JSON, lo valida contra el modelo y devuelve un 422 con el detalle si no
    encaja. Cuando el cuerpo de la función se ejecuta, `match` ya es válido.

    Devuelve 201 Created, no 200. La diferencia importa: 201 significa "se creó un
    recurso nuevo", y es lo que un cliente HTTP espera de un POST que crea algo.
    """
    document = match_to_document(match)

    collection = get_database()[COLLECTION]
    # await porque es E/S de red: mientras Mongo responde, el bucle de eventos
    # atiende otras peticiones en lugar de quedarse bloqueado.
    result = await collection.insert_one(document)

    # insert_one no devuelve el documento, solo el _id generado. Como ya tenemos
    # el documento en memoria, lo completamos en vez de pedirlo otra vez a la base:
    # sería un viaje de red innecesario.
    document["_id"] = result.inserted_id
    return match_from_document(document)


@router.get("", response_model=list[MatchOut])
async def list_matches() -> list[MatchOut]:
    """Devuelve todas las partidas, de la más reciente a la más antigua.

    Sin paginación a propósito: con veinte partidas no hace falta, y añadirla ahora
    sería abstracción especulativa. Cuando la lista crezca, aquí entran los
    parámetros skip y limit.
    """
    collection = get_database()[COLLECTION]

    # find() no ejecuta nada todavía: devuelve un cursor. La consulta sale hacia
    # Mongo cuando se empieza a iterar.
    cursor = collection.find().sort("played_at", -1)

    # `async for` porque cada lote de documentos llega por la red. to_list() sería
    # más corto, pero esto deja ver que los resultados llegan en tandas, no de golpe.
    return [match_from_document(document) async for document in cursor]
