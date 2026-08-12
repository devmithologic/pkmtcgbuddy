"""Endpoints del recurso /api/decks.

Los mazos son datos nuestros —a diferencia de las cartas, que son de TCGdex— así
que aquí sí hay escritura. La validación se calcula en cada lectura y nunca se
guarda.
"""

from datetime import date

from fastapi import APIRouter, HTTPException, Query, status

from app.db import card_repository, deck_repository, stats_repository
from app.models.card import DeckFormat
from app.models.deck import (
    DeckCard,
    DeckCardOut,
    DeckCardsUpdate,
    DeckCreate,
    DeckOut,
    DeckSummary,
    DeckValidation,
    DeckVersionOut,
    DeckVersionSummary,
    NewVersionRequest,
)
from app.models.session import SessionType
from app.models.stats import DeckStats, StatLine, StatsFilters, VersionStatLine
from app.services.deck_rules import validate_deck

router = APIRouter(prefix="/decks", tags=["decks"])


async def _resolve(cards_raw: list[dict], deck_format: DeckFormat):
    """Convierte la lista almacenada en su forma resuelta y la valida.

    Una sola consulta al catálogo sirve para las dos cosas.
    """
    cards = [DeckCard(**c) for c in cards_raw]
    catalogue = await card_repository.get_cards_by_ids([c.card_id for c in cards])

    resolved = [
        DeckCardOut(
            quantity=entry.quantity,
            card=catalogue[entry.card_id],
            category=catalogue[entry.card_id].category.value,
            is_ace_spec=catalogue[entry.card_id].is_ace_spec,
            is_basic_energy=catalogue[entry.card_id].is_basic_energy,
            legal_in_format=catalogue[entry.card_id].is_legal_in(deck_format),
        )
        for entry in cards
        if entry.card_id in catalogue
    ]

    return resolved, validate_deck(cards, catalogue, deck_format)


async def _load_deck(deck_id: str) -> dict:
    """Busca un mazo o lanza 404. Centralizado porque lo necesitan casi todas."""
    oid = deck_repository.to_object_id(deck_id)
    deck = await deck_repository.get_deck(oid) if oid else None

    if deck is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"No existe el mazo {deck_id}"
        )
    return deck


@router.post("", response_model=DeckOut, status_code=status.HTTP_201_CREATED)
async def create_deck(payload: DeckCreate) -> DeckOut:
    """Crea un mazo con su versión 1, vacía."""
    deck_id = await deck_repository.create_deck(payload.name, payload.deck_format)
    return await get_deck(deck_id)


@router.get("", response_model=list[DeckSummary])
async def list_decks() -> list[DeckSummary]:
    """Listado con el estado de validez de cada mazo."""
    summaries = []

    for doc in await deck_repository.list_decks():
        current = doc.get("current") or {}
        deck_format = DeckFormat(doc["format"])
        _, validation = await _resolve(current.get("cards", []), deck_format)

        summaries.append(
            DeckSummary(
                id=str(doc["_id"]),
                name=doc["name"],
                deck_format=deck_format,
                current_version=current.get("version", 1),
                current_version_id=str(doc["current_version_id"]),
                total_cards=validation.total_cards,
                is_legal=validation.is_legal,
                updated_at=doc["updated_at"],
            )
        )

    return summaries


@router.get("/{deck_id}", response_model=DeckOut)
async def get_deck(deck_id: str) -> DeckOut:
    """Mazo, lista de la versión actual y validación."""
    deck = await _load_deck(deck_id)
    version = await deck_repository.get_version(deck["current_version_id"])

    if version is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="El mazo apunta a una versión que no existe",
        )

    deck_format = DeckFormat(deck["format"])
    resolved, validation = await _resolve(version["cards"], deck_format)

    return DeckOut(
        id=str(deck["_id"]),
        name=deck["name"],
        deck_format=deck_format,
        current_version=DeckVersionOut(
            id=str(version["_id"]),
            version=version["version"],
            message=version["message"],
            total_cards=validation.total_cards,
            created_at=version["created_at"],
            cards=resolved,
        ),
        validation=validation,
        created_at=deck["created_at"],
        updated_at=deck["updated_at"],
    )


@router.put("/{deck_id}/cards", response_model=DeckOut)
async def replace_cards(deck_id: str, payload: DeckCardsUpdate) -> DeckOut:
    """Reemplaza la lista de la versión ACTUAL.

    Se guarda cualquier estado, legal o no: construir un mazo es iterativo, y
    negarse a guardar 30 cartas porque no son 60 haría la aplicación inservible.
    La respuesta incluye la validación, así que el cliente sabe qué le falta.

    Solo la versión actual es editable. Las anteriores están congeladas — es lo
    que hace que las estadísticas atribuidas a ellas sigan siendo ciertas.
    """
    deck = await _load_deck(deck_id)
    await deck_repository.replace_cards(deck["current_version_id"], payload.cards)
    return await get_deck(deck_id)


@router.post(
    "/{deck_id}/versions", response_model=DeckOut, status_code=status.HTTP_201_CREATED
)
async def create_version(deck_id: str, payload: NewVersionRequest) -> DeckOut:
    """Crea una versión nueva copiando la lista de la actual.

    A partir de aquí, la anterior queda congelada y los cambios van a la nueva.
    """
    deck = await _load_deck(deck_id)
    await deck_repository.create_version(deck, payload.message)
    return await get_deck(deck_id)


@router.get("/{deck_id}/versions", response_model=list[DeckVersionSummary])
async def list_versions(deck_id: str) -> list[DeckVersionSummary]:
    """Historial del mazo, de la versión más reciente a la más antigua."""
    deck = await _load_deck(deck_id)
    return await deck_repository.list_versions(deck["_id"])


@router.get("/{deck_id}/versions/{version_id}", response_model=DeckVersionOut)
async def get_version(deck_id: str, version_id: str) -> DeckVersionOut:
    """Una versión concreta con su lista. Sirve para mirar el pasado."""
    deck = await _load_deck(deck_id)
    oid = deck_repository.to_object_id(version_id)
    version = await deck_repository.get_version(oid) if oid else None

    # Se comprueba que la versión pertenece a ESTE mazo. Sin ello,
    # /decks/{otro}/versions/{id} devolvería datos ajenos: un fallo de control de
    # acceso por referencia directa a objeto.
    if version is None or version["deck_id"] != deck["_id"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"El mazo {deck_id} no tiene la versión {version_id}",
        )

    resolved, validation = await _resolve(version["cards"], DeckFormat(deck["format"]))

    return DeckVersionOut(
        id=str(version["_id"]),
        version=version["version"],
        message=version["message"],
        total_cards=validation.total_cards,
        created_at=version["created_at"],
        cards=resolved,
    )


@router.get("/{deck_id}/stats", response_model=DeckStats)
async def deck_stats(
    deck_id: str,
    date_from: date | None = Query(default=None, description="Desde, inclusive"),
    date_to: date | None = Query(default=None, description="Hasta, inclusive"),
    session_type: SessionType | None = Query(default=None),
) -> DeckStats:
    """Estadísticas del mazo, agregadas sobre las sesiones jugadas con él.

    El desglose por versión es la razón de ser de todo esto: saber si la v2 juega
    mejor que la v1 es la pregunta que ningún tracker comercial responde.

    Los filtros de periodo y tipo de evento no son adorno. Un win rate que mezcla
    testing con torneo no describe ninguna de las dos cosas: contra tu amigo
    pruebas líneas raras y aceptas perder.
    """
    deck = await _load_deck(deck_id)

    # Una sesión referencia una VERSIÓN, así que para las estadísticas del mazo
    # entero hay que reunir todas sus versiones primero.
    versions = await deck_repository.list_versions(deck["_id"])
    version_ids = [deck_repository.to_object_id(v.id) for v in versions]
    por_id = {v.id: v for v in versions}

    raw = await stats_repository.deck_stats(
        version_ids, date_from=date_from, date_to=date_to, session_type=session_type
    )

    def linea(row: dict, label: str) -> StatLine:
        return StatLine(
            label=label, wins=row["wins"], losses=row["losses"], ties=row["ties"]
        )

    overall = (
        linea(raw["overall"][0], deck["name"])
        if raw["overall"]
        else StatLine(label=deck["name"], wins=0, losses=0, ties=0)
    )

    by_version = []
    for row in raw["by_version"]:
        version = por_id.get(str(row["_id"]))
        if version is None:
            # Una sesión apunta a una versión que ya no existe. No debería pasar
            # —no hay forma de borrar versiones— pero si pasara, se omite en vez
            # de reventar la pantalla entera.
            continue
        by_version.append(
            VersionStatLine(
                label=f"v{version.version}",
                version=version.version,
                version_id=version.id,
                message=version.message,
                wins=row["wins"],
                losses=row["losses"],
                ties=row["ties"],
            )
        )
    by_version.sort(key=lambda v: v.version)

    return DeckStats(
        deck_id=str(deck["_id"]),
        deck_name=deck["name"],
        filters=StatsFilters(
            date_from=date_from, date_to=date_to, session_type=session_type
        ),
        sessions_counted=raw["sessions"],
        overall=overall,
        by_version=by_version,
        by_archetype=[linea(r, r["_id"]) for r in raw["by_archetype"]],
        by_session_type=[linea(r, r["_id"]) for r in raw["by_session_type"]],
    )
