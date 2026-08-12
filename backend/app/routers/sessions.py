"""Endpoints del recurso /api/sessions.

Las partidas son una subcolección: viven bajo `/api/sessions/{id}/matches` porque
no existen fuera de su sesión. Que la URL lo refleje no es estética — le dice al
cliente que no hay forma de pedir una partida suelta, que es exactamente la
verdad del modelo.

Toda operación sobre una ronda devuelve la SESIÓN entera actualizada, igual que
`PUT /api/decks/{id}/cards`. Así el cliente nunca recalcula el récord: llega
hecho, y no hay dos versiones del cálculo que puedan discrepar.
"""

from fastapi import APIRouter, HTTPException, status

from app.db import deck_repository, session_repository
from app.db.mongo import to_object_id
from app.models.match import date_from_bson
from app.models.session import (
    MatchCreate,
    MatchOut,
    SessionCreate,
    SessionOut,
    SessionSummary,
    compute_record,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])


async def _load(session_id: str) -> dict:
    oid = to_object_id(session_id)
    session = await session_repository.get_session(oid) if oid else None

    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe la sesión {session_id}",
        )
    return session


def _to_out(session: dict, deck: dict | None) -> SessionOut:
    return SessionOut(
        id=str(session["_id"]),
        played_at=date_from_bson(session["played_at"]),
        session_type=session["session_type"],
        name=session.get("name"),
        notes=session.get("notes"),
        deck_version_id=str(session["deck_version_id"]),
        deck_name=(deck or {}).get("name"),
        deck_version=(deck or {}).get("version"),
        record=compute_record(session["matches"]),
        matches=[MatchOut(**m) for m in session["matches"]],
        created_at=session["created_at"],
    )


async def _respond(session_id: str) -> SessionOut:
    """Relee la sesión y la devuelve resuelta. Un solo camino de salida para
    todas las mutaciones, así no hay dos formas de construir la respuesta."""
    session = await _load(session_id)
    decks = await session_repository.resolve_decks([session])
    return _to_out(session, decks.get(session["deck_version_id"]))


@router.post("", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
async def create_session(payload: SessionCreate) -> SessionOut:
    """Crea una sesión vacía. Las rondas se añaden después, según se juegan."""
    # Se valida el mazo ANTES de crear nada. Sin esto una sesión podría apuntar a
    # una versión inventada y las estadísticas de la fase 4 tendrían que lidiar
    # con referencias rotas.
    oid = to_object_id(payload.deck_version_id)
    version = await deck_repository.get_version(oid) if oid else None
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"No existe la versión de mazo {payload.deck_version_id}",
        )

    session_id = await session_repository.create_session(payload)
    return await _respond(str(session_id))


@router.get("", response_model=list[SessionSummary])
async def list_sessions() -> list[SessionSummary]:
    """Listado, de la sesión más reciente a la más antigua."""
    sessions = await session_repository.list_sessions()
    decks = await session_repository.resolve_decks(sessions)

    return [
        SessionSummary(
            id=str(s["_id"]),
            played_at=date_from_bson(s["played_at"]),
            session_type=s["session_type"],
            name=s.get("name"),
            deck_name=decks.get(s["deck_version_id"], {}).get("name"),
            deck_version=decks.get(s["deck_version_id"], {}).get("version"),
            record=compute_record(s["matches"]),
        )
        for s in sessions
    ]


@router.get("/{session_id}", response_model=SessionOut)
async def get_session(session_id: str) -> SessionOut:
    """Una sesión con sus rondas y su récord."""
    return await _respond(session_id)


@router.post(
    "/{session_id}/matches", response_model=SessionOut, status_code=status.HTTP_201_CREATED
)
async def add_match(session_id: str, payload: MatchCreate) -> SessionOut:
    """Añade una ronda al final de la sesión."""
    session = await _load(session_id)
    await session_repository.add_match(session["_id"], payload)
    return await _respond(session_id)


@router.put("/{session_id}/matches/{round_no}", response_model=SessionOut)
async def update_match(session_id: str, round_no: int, payload: MatchCreate) -> SessionOut:
    """Corrige una ronda ya registrada. Te equivocaste de arquetipo, o de
    resultado."""
    session = await _load(session_id)

    if not await session_repository.update_match(session["_id"], round_no, payload):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"La sesión no tiene una ronda {round_no}",
        )
    return await _respond(session_id)


@router.delete("/{session_id}/matches/{round_no}", response_model=SessionOut)
async def delete_match(session_id: str, round_no: int) -> SessionOut:
    """Borra una ronda. Las siguientes se renumeran para no dejar huecos."""
    session = await _load(session_id)

    if not await session_repository.delete_match(session["_id"], round_no):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"La sesión no tiene una ronda {round_no}",
        )
    return await _respond(session_id)
