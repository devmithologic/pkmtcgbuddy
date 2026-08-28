"""Endpoints for the /api/sessions resource.

Games are a subcollection: they live under `/api/sessions/{id}/matches`
because they don't exist outside their session. Having the URL reflect that
isn't aesthetics — it tells the client there's no way to request a
standalone game, which is exactly the truth of the model.

Every operation on a round returns the whole updated SESSION, the same as
`PUT /api/decks/{id}/cards`. That way the client never recomputes the
record: it arrives already done, and there aren't two versions of the
calculation that could disagree.
"""

from fastapi import APIRouter, HTTPException, Query, status

from app.db import deck_repository, session_repository
from app.db.mongo import to_object_id
from app.models.match import date_from_bson
from app.models.session import (
    MatchCreate,
    MatchOut,
    SessionCreate,
    SessionOut,
    SessionSummary,
    SessionUpdate,
    TagCount,
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
        tags=session.get("tags", []),
        matches=[MatchOut(**m) for m in session["matches"]],
        created_at=session["created_at"],
    )


async def _respond(session_id: str) -> SessionOut:
    """Rereads the session and returns it resolved. A single exit path for
    all mutations, so there aren't two ways to build the response."""
    session = await _load(session_id)
    decks = await session_repository.resolve_decks([session])
    return _to_out(session, decks.get(session["deck_version_id"]))


@router.post("", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
async def create_session(payload: SessionCreate) -> SessionOut:
    """Creates an empty session. Rounds are added afterward, as they're played."""
    # The deck is validated BEFORE creating anything. Without this a session
    # could end up pointing at a made-up version, and phase 4's statistics
    # would have to deal with broken references.
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
async def list_sessions(
    tag: str | None = Query(default=None, description="Filtra por etiqueta"),
) -> list[SessionSummary]:
    """Listing, from the most recent session to the oldest."""
    sessions = await session_repository.list_sessions(tag=tag)
    decks = await session_repository.resolve_decks(sessions)

    return [
        SessionSummary(
            id=str(s["_id"]),
            played_at=date_from_bson(s["played_at"]),
            session_type=s["session_type"],
            name=s.get("name"),
            deck_name=decks.get(s["deck_version_id"], {}).get("name"),
            deck_version=decks.get(s["deck_version_id"], {}).get("version"),
            deck_primary=decks.get(s["deck_version_id"], {}).get("primary"),
            deck_secondary=decks.get(s["deck_version_id"], {}).get("secondary"),
            record=compute_record(s["matches"]),
            tags=s.get("tags", []),
        )
        for s in sessions
    ]


# NOTE: this route goes BEFORE /{session_id}. FastAPI resolves by declaration
# order, so if /{session_id} came first, "tags" would be read as a session id
# and this would return 404.
@router.get("/tags", response_model=list[TagCount])
async def list_tags() -> list[TagCount]:
    """Tags in use, with their number of sessions."""
    return [TagCount(**t) for t in await session_repository.list_tags()]


@router.get("/{session_id}", response_model=SessionOut)
async def get_session(session_id: str) -> SessionOut:
    """A session with its rounds and its record."""
    return await _respond(session_id)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(session_id: str) -> None:
    """Deletes the session and all its rounds.

    204 No Content: the operation went fine and there's nothing to return.
    Returning the deleted session would be contradictory.
    """
    session = await _load(session_id)
    await session_repository.delete_session(session["_id"])


@router.patch("/{session_id}", response_model=SessionOut)
async def update_session(session_id: str, payload: SessionUpdate) -> SessionOut:
    """Corrects the session's data: date, type, deck, name or notes.

    Rounds don't go through here: each one is saved when it's added. This is
    for the event's header, which until now stayed frozen once created.
    """
    session = await _load(session_id)

    # If the deck changes, it's validated the same as when creating. Without
    # this, a correction could leave the session pointing at a made-up
    # version.
    if payload.deck_version_id is not None:
        oid = to_object_id(payload.deck_version_id)
        version = await deck_repository.get_version(oid) if oid else None
        if version is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"No existe la versión de mazo {payload.deck_version_id}",
            )

    await session_repository.update_session(session["_id"], payload)
    return await _respond(session_id)


@router.post(
    "/{session_id}/matches", response_model=SessionOut, status_code=status.HTTP_201_CREATED
)
async def add_match(session_id: str, payload: MatchCreate) -> SessionOut:
    """Adds a round at the end of the session."""
    session = await _load(session_id)
    await session_repository.add_match(session["_id"], payload)
    return await _respond(session_id)


@router.put("/{session_id}/matches/{round_no}", response_model=SessionOut)
async def update_match(session_id: str, round_no: int, payload: MatchCreate) -> SessionOut:
    """Corrects a round already recorded. You got the archetype wrong, or the
    result."""
    session = await _load(session_id)

    if not await session_repository.update_match(session["_id"], round_no, payload):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"La sesión no tiene una ronda {round_no}",
        )
    return await _respond(session_id)


@router.delete("/{session_id}/matches/{round_no}", response_model=SessionOut)
async def delete_match(session_id: str, round_no: int) -> SessionOut:
    """Deletes a round. The following ones are renumbered so there are no gaps."""
    session = await _load(session_id)

    if not await session_repository.delete_match(session["_id"], round_no):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"La sesión no tiene una ronda {round_no}",
        )
    return await _respond(session_id)
