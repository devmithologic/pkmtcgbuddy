"""Endpoints del recurso /api/matches."""

from fastapi import APIRouter, HTTPException, status

from app.db import deck_repository
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


async def _resolve_decks(documents: list[dict]) -> dict:
    """Resuelve {version_id: {name, version}} para un lote de partidas.

    Dos consultas para toda la lista, pase la que pase: una a deck_versions y
    otra a decks. La alternativa evidente —buscar el mazo de cada partida dentro
    del bucle— serían 2 consultas por partida. Es el mismo N+1 de
    log_mentor/08, y aquí se evita igual: agrupar los ids y pedirlos con $in.
    """
    version_ids = {d["deck_version_id"] for d in documents if d.get("deck_version_id")}
    if not version_ids:
        return {}

    db = get_database()

    versions = {
        v["_id"]: v
        async for v in db["deck_versions"].find({"_id": {"$in": list(version_ids)}})
    }
    deck_ids = {v["deck_id"] for v in versions.values()}
    decks = {d["_id"]: d async for d in db["decks"].find({"_id": {"$in": list(deck_ids)}})}

    return {
        vid: {
            "name": decks.get(v["deck_id"], {}).get("name"),
            "version": v["version"],
        }
        for vid, v in versions.items()
    }


@router.post("", response_model=MatchOut, status_code=status.HTTP_201_CREATED)
async def create_match(match: MatchCreate) -> MatchOut:
    """Registra una partida.

    El parámetro anotado con MatchCreate es lo que hace el trabajo: FastAPI lee el
    cuerpo JSON, lo valida contra el modelo y devuelve un 422 con el detalle si no
    encaja. Cuando el cuerpo de la función se ejecuta, `match` ya es válido.

    Devuelve 201 Created, no 200. La diferencia importa: 201 significa "se creó un
    recurso nuevo", y es lo que un cliente HTTP espera de un POST que crea algo.
    """
    # Se comprueba que la versión existe ANTES de guardar. Sin esto, una partida
    # podría apuntar a una versión inventada y las estadísticas de la fase 4
    # tendrían que lidiar con referencias rotas.
    if match.deck_version_id:
        oid = deck_repository.to_object_id(match.deck_version_id)
        version = await deck_repository.get_version(oid) if oid else None
        if version is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"No existe la versión de mazo {match.deck_version_id}",
            )

    document = match_to_document(match)

    collection = get_database()[COLLECTION]
    # await porque es E/S de red: mientras Mongo responde, el bucle de eventos
    # atiende otras peticiones en lugar de quedarse bloqueado.
    result = await collection.insert_one(document)

    # insert_one no devuelve el documento, solo el _id generado. Como ya tenemos
    # el documento en memoria, lo completamos en vez de pedirlo otra vez a la base.
    document["_id"] = result.inserted_id
    decks = await _resolve_decks([document])

    return match_from_document(document, decks.get(document.get("deck_version_id")))


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
    documents = [document async for document in cursor]

    decks = await _resolve_decks(documents)

    return [
        match_from_document(doc, decks.get(doc.get("deck_version_id")))
        for doc in documents
    ]
