"""Endpoints for the /api/decks resource.

Decks are our own data —unlike cards, which belong to TCGdex— so this is where
writes happen. Validation is computed on every read and never stored.
"""

from datetime import date

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import PlainTextResponse

from app.db import card_repository, deck_repository, set_repository, stats_repository
from app.models.card import DeckFormat
from app.models.deck import (
    DeckCard,
    DeckCardOut,
    DeckCardsUpdate,
    DeckCreate,
    DeckImport,
    DeckImportResult,
    DeckOut,
    DeckSummary,
    DeckUpdate,
    DeckValidation,
    DeckVersionOut,
    DeckVersionSummary,
    NewVersionRequest,
)
from app.models.session import SessionType
from app.models.stats import DeckStats, StatLine, StatsFilters, VersionStatLine
from app.services import deck_text
from app.services.deck_rules import validate_deck

router = APIRouter(prefix="/decks", tags=["decks"])


async def _resolve(cards_raw: list[dict], deck_format: DeckFormat):
    """Converts the stored decklist into its resolved form and validates it.

    A single query to the catalogue serves both purposes.
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
    """Looks up a deck or raises 404. Centralized because almost every endpoint needs it."""
    oid = deck_repository.to_object_id(deck_id)
    deck = await deck_repository.get_deck(oid) if oid else None

    if deck is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"No existe el mazo {deck_id}"
        )
    return deck


@router.post("", response_model=DeckOut, status_code=status.HTTP_201_CREATED)
async def create_deck(payload: DeckCreate) -> DeckOut:
    """Creates a deck with its version 1, empty."""
    deck_id = await deck_repository.create_deck(
        payload.name,
        payload.deck_format,
        deck_repository.to_object_id(payload.folder_id) if payload.folder_id else None,
    )

    # Icons are optional at creation; if they came in, they're applied in the
    # same step by reusing the PATCH instead of duplicating the write.
    if payload.primary_pokemon or payload.secondary_pokemon:
        await deck_repository.update_deck(
            deck_repository.to_object_id(deck_id),
            DeckUpdate(
                primary_pokemon=payload.primary_pokemon,
                secondary_pokemon=payload.secondary_pokemon,
            ),
        )

    return await get_deck(deck_id)


@router.get("", response_model=list[DeckSummary])
async def list_decks() -> list[DeckSummary]:
    """List with the validity state of every deck.

    The catalogue for ALL decks is resolved in ONE query before the loop.
    The first version called `_resolve` inside the loop, and `_resolve` does
    its own get_cards_by_ids: 20 decks were 21 round trips. The repository had
    gone to the trouble of using a $lookup to avoid the N+1, and the router was
    reintroducing it one layer up — avoiding it in one place is worthless if it
    gets recreated in the other.
    """
    docs = await deck_repository.list_decks()

    todos_los_ids = [
        c["card_id"]
        for doc in docs
        for c in (doc.get("current") or {}).get("cards", [])
    ]
    catalogo = await card_repository.get_cards_by_ids(todos_los_ids)

    summaries = []
    for doc in docs:
        current = doc.get("current") or {}
        deck_format = DeckFormat(doc["format"])
        cards = [DeckCard(**c) for c in current.get("cards", [])]
        validation = validate_deck(cards, catalogo, deck_format)

        # A deck with no version shouldn't exist —create_deck isn't
        # transactional and a failure between the two inserts would leave it
        # this way— but if it does exist, str(None) would give the string
        # "None" and starting a session with it would produce a confusing
        # 422. It's left out of the listing.
        if doc.get("current_version_id") is None:
            continue

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
                primary_pokemon=doc.get("primary_pokemon"),
                secondary_pokemon=doc.get("secondary_pokemon"),
                folder_id=str(doc["folder_id"]) if doc.get("folder_id") else None,
            )
        )

    return summaries


@router.post("/import", response_model=DeckImportResult, status_code=status.HTTP_201_CREATED)
async def import_deck(payload: DeckImport) -> DeckImportResult:
    """Creates a deck from a decklist in the PTCG Live text format.

    Declared BEFORE `/{deck_id}` — FastAPI resolves by declaration order, and
    with the other one first, "import" would be read as a deck id. It's the
    same trap `/sessions/tags` already documents.

    Imports what it recognizes and returns what it doesn't, instead of
    rejecting the whole list over one line. A friend's list may bring a card
    from a set we haven't synced, and ending up with nothing because of that
    is worse than ending up with 57 of 60 while knowing which ones are
    missing.
    """
    lineas, sueltas = deck_text.parse(payload.text)
    if not lineas:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "No se reconoció ninguna carta. El formato es «3 Riolu PRE 50», una por línea.",
        )

    abreviaturas = await set_repository.abbreviation_map()

    # A single query for the whole list: the candidate ids from each line are
    # accumulated and requested together. Resolving line by line would be 23
    # round trips.
    candidatos: list[str] = []
    por_linea: list[tuple[deck_text.ParsedLine, list[str]]] = []
    for linea in lineas:
        set_id = abreviaturas.get(linea.set_code)
        ids = deck_text.candidate_ids(set_id, linea.number) if set_id else []
        candidatos.extend(ids)
        por_linea.append((linea, ids))

    catalogo = await card_repository.get_cards_by_ids(candidatos)

    cards: list[DeckCard] = []
    no_resueltas: list[str] = list(sueltas)
    for linea, ids in por_linea:
        encontrado = next((i for i in ids if i in catalogo), None)
        if encontrado:
            cards.append(DeckCard(card_id=encontrado, quantity=linea.quantity))
        else:
            no_resueltas.append(linea.raw)

    if not cards:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Ninguna carta de la lista está en el catálogo. "
            "¿Has sincronizado los sets con `python -m app.services.set_sync`?",
        )

    # The text format says nothing about the tournament format or the deck's
    # name: neither one travels in the list. The name is set by whoever
    # imports it, and the format is left at Standard, which is what's played
    # and gets changed in the builder's header with one click.
    deck_id = await deck_repository.create_deck(
        payload.name or "Mazo importado",
        DeckFormat.STANDARD,
        deck_repository.to_object_id(payload.folder_id) if payload.folder_id else None,
    )
    deck = await deck_repository.get_deck(deck_repository.to_object_id(deck_id))
    await deck_repository.replace_cards(deck["current_version_id"], cards)

    return DeckImportResult(
        deck=await get_deck(deck_id),
        imported_cards=sum(c.quantity for c in cards),
        unresolved=no_resueltas,
    )


@router.get("/{deck_id}/export", response_class=PlainTextResponse)
async def export_deck(deck_id: str) -> str:
    """The deck's current decklist in the text format, ready to paste.

    Returned as text/plain and not inside a JSON: it's a document, not data,
    so `curl` or the browser already give back something that can be copied
    as-is.
    """
    deck = await _load_deck(deck_id)
    version = await deck_repository.get_version(deck["current_version_id"])
    entradas = [DeckCard(**c) for c in (version or {}).get("cards", [])]

    catalogo = await card_repository.get_cards_by_ids([e.card_id for e in entradas])
    codigos = await set_repository.id_map()

    salida = []
    for entrada in entradas:
        carta = catalogo.get(entrada.card_id)
        if not carta:
            continue
        set_id, _, numero = entrada.card_id.rpartition("-")
        salida.append(
            {
                "quantity": entrada.quantity,
                "name": carta.name,
                "category": carta.category.value,
                "set_code": codigos.get(set_id),
                # No leading zeros: it's how the other tools write it, and how
                # it's printed on the card.
                "number": deck_text.normalize_number(numero),
            }
        )

    return deck_text.render(salida)


@router.get("/{deck_id}", response_model=DeckOut)
async def get_deck(deck_id: str) -> DeckOut:
    """Deck, current version's decklist, and validation."""
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
        primary_pokemon=deck.get("primary_pokemon"),
        secondary_pokemon=deck.get("secondary_pokemon"),
        folder_id=str(deck["folder_id"]) if deck.get("folder_id") else None,
    )


@router.delete("/{deck_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_deck(deck_id: str) -> None:
    """Deletes a deck and its version history.

    **Refused if any session was played with it**, returning a 409 that says
    how many. This isn't generic caution: the central idea of this application
    is that every game is attributed to the VERSION it was played with, so
    deleting the deck would leave those sessions pointing at a document that
    no longer exists. The record would still exist, but it would no longer be
    known which list it was: exactly the data this application exists to
    preserve.

    409 Conflict and not 400: the request is well-formed, what happens is that
    it conflicts with the resource's current state. And not 403, which would
    speak of permissions.

    Leaves the way out to the user: delete those sessions first, or keep the
    deck. Cascading the delete would be deciding the most destructive option
    for them.
    """
    deck = await _load_deck(deck_id)

    en_uso = await deck_repository.sessions_using(deck["_id"])
    if en_uso:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"No se puede borrar: {en_uso} "
            f"{'sesión se jugó' if en_uso == 1 else 'sesiones se jugaron'} con este mazo. "
            "Bórralas primero si de verdad quieres eliminarlo.",
        )

    await deck_repository.delete_deck(deck["_id"])


@router.patch("/{deck_id}", response_model=DeckOut)
async def update_deck(deck_id: str, payload: DeckUpdate) -> DeckOut:
    """Changes the name or icons of a deck that already exists.

    PATCH and not PUT because a partial change is sent, not the whole
    resource. That's the semantic difference between the two verbs, and it
    matters here: a PUT would force resending the entire deck just to change
    one icon.
    """
    deck = await _load_deck(deck_id)
    await deck_repository.update_deck(deck["_id"], payload)
    return await get_deck(deck_id)


@router.put("/{deck_id}/cards", response_model=DeckOut)
async def replace_cards(deck_id: str, payload: DeckCardsUpdate) -> DeckOut:
    """Replaces the CURRENT version's decklist.

    Any state is saved, legal or not: building a deck is iterative, and
    refusing to save 30 cards because they aren't 60 would make the
    application useless. The response includes the validation, so the client
    knows what's missing.

    Only the current version is editable. Earlier ones are frozen — that's
    what keeps the statistics attributed to them true.
    """
    deck = await _load_deck(deck_id)
    await deck_repository.replace_cards(deck["current_version_id"], payload.cards)
    return await get_deck(deck_id)


@router.post(
    "/{deck_id}/versions", response_model=DeckOut, status_code=status.HTTP_201_CREATED
)
async def create_version(deck_id: str, payload: NewVersionRequest) -> DeckOut:
    """Creates a new version by copying the current one's decklist.

    From here on, the previous one is frozen and changes go to the new one.
    """
    deck = await _load_deck(deck_id)
    await deck_repository.create_version(deck, payload.message)
    return await get_deck(deck_id)


@router.get("/{deck_id}/versions", response_model=list[DeckVersionSummary])
async def list_versions(deck_id: str) -> list[DeckVersionSummary]:
    """The deck's history, from the most recent version to the oldest."""
    deck = await _load_deck(deck_id)
    return await deck_repository.list_versions(deck["_id"])


@router.get("/{deck_id}/versions/{version_id}", response_model=DeckVersionOut)
async def get_version(deck_id: str, version_id: str) -> DeckVersionOut:
    """A specific version with its decklist. Useful for looking at the past."""
    deck = await _load_deck(deck_id)
    oid = deck_repository.to_object_id(version_id)
    version = await deck_repository.get_version(oid) if oid else None

    # It's checked that the version belongs to THIS deck. Without that,
    # /decks/{other}/versions/{id} would return someone else's data: an
    # insecure direct object reference access-control flaw.
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
    tag: str | None = Query(default=None, description="Filtra por etiqueta de sesión"),
) -> DeckStats:
    """Deck statistics, aggregated over the sessions played with it.

    The breakdown by version is the whole reason this exists: knowing whether
    v2 plays better than v1 is the question no commercial tracker answers.

    The period and event-type filters aren't decoration. A win rate that mixes
    testing with tournament describes neither: against a friend you try out
    weird lines and accept losing.
    """
    deck = await _load_deck(deck_id)

    # A session references a VERSION, so the statistics for the whole deck
    # require gathering all its versions first.
    versions = await deck_repository.list_versions(deck["_id"])
    version_ids = [deck_repository.to_object_id(v.id) for v in versions]
    por_id = {v.id: v for v in versions}

    raw = await stats_repository.deck_stats(
        version_ids,
        date_from=date_from,
        date_to=date_to,
        session_type=session_type,
        tag=tag,
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
            # A session points at a version that no longer exists. Shouldn't
            # happen —there's no way to delete versions— but if it did, it's
            # skipped instead of blowing up the whole screen.
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
            date_from=date_from, date_to=date_to, session_type=session_type, tag=tag
        ),
        sessions_counted=raw["sessions"],
        overall=overall,
        by_version=by_version,
        by_archetype=[linea(r, r["_id"]) for r in raw["by_archetype"]],
        by_session_type=[linea(r, r["_id"]) for r in raw["by_session_type"]],
    )
