"""Endpoints del recurso /api/decks.

Los mazos son datos nuestros —a diferencia de las cartas, que son de TCGdex— así
que aquí sí hay escritura. La validación se calcula en cada lectura y nunca se
guarda.
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
    deck_id = await deck_repository.create_deck(
        payload.name,
        payload.deck_format,
        deck_repository.to_object_id(payload.folder_id) if payload.folder_id else None,
    )

    # Los iconos son opcionales al crear; si vinieron, se aplican en el mismo
    # paso reutilizando el PATCH en lugar de duplicar la escritura.
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
    """Listado con el estado de validez de cada mazo.

    El catálogo de TODOS los mazos se resuelve en UNA consulta antes del bucle.
    La primera versión llamaba a `_resolve` dentro del bucle, y `_resolve` hace
    su propio get_cards_by_ids: 20 mazos eran 21 viajes. El repositorio se había
    molestado en usar un $lookup para evitar el N+1 y el router lo reintroducía
    una capa más arriba — evitarlo en un sitio no sirve si se recrea en el otro.
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

        # Un mazo sin versión no debería existir —create_deck no es
        # transaccional y un fallo entre las dos inserciones lo dejaría así—
        # pero si existe, str(None) daría la cadena "None" y al empezar una
        # sesión con él saldría un 422 desconcertante. Se omite del listado.
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
    """Crea un mazo a partir de una lista en el formato de texto de PTCG Live.

    Va declarada ANTES que `/{deck_id}` — FastAPI resuelve por orden, y con la
    otra primero «import» se leería como un id de mazo. Es la misma trampa que
    ya documenta `/sessions/tags`.

    Importa lo que reconoce y devuelve lo que no, en vez de rechazar la lista
    entera por una línea. Una lista ajena puede traer una carta de un set que no
    hemos sincronizado, y quedarse sin nada por eso es peor que quedarse con 57
    de 60 sabiendo cuáles faltan.
    """
    lineas, sueltas = deck_text.parse(payload.text)
    if not lineas:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "No se reconoció ninguna carta. El formato es «3 Riolu PRE 50», una por línea.",
        )

    abreviaturas = await set_repository.abbreviation_map()

    # Una sola consulta para toda la lista: se acumulan los ids candidatos de
    # cada línea y se piden juntos. Resolver línea a línea serían 23 viajes.
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

    # El formato de texto no dice el formato de torneo ni el nombre del mazo:
    # ninguno de los dos viaja en la lista. El nombre lo pone quien importa, y
    # el formato se deja en Standard, que es lo que se juega y se cambia en la
    # cabecera del constructor con un clic.
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
    """La lista actual del mazo en el formato de texto, lista para pegar.

    Se devuelve como text/plain y no dentro de un JSON: es un documento, no un
    dato, y así `curl` o el navegador ya dan algo que se copia tal cual.
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
                # Sin ceros a la izquierda: es como lo escriben las demás
                # herramientas, y como se imprime en la carta.
                "number": deck_text.normalize_number(numero),
            }
        )

    return deck_text.render(salida)


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
        primary_pokemon=deck.get("primary_pokemon"),
        secondary_pokemon=deck.get("secondary_pokemon"),
        folder_id=str(deck["folder_id"]) if deck.get("folder_id") else None,
    )


@router.delete("/{deck_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_deck(deck_id: str) -> None:
    """Borra un mazo y su historial de versiones.

    **Se niega si alguna sesión se jugó con él**, y devuelve 409 diciendo
    cuántas. No es prudencia genérica: la idea central de esta aplicación es que
    cada partida se atribuye a la VERSIÓN con la que se jugó, así que borrar el
    mazo dejaría esas sesiones apuntando a un documento inexistente. El récord
    seguiría existiendo, pero ya no se sabría de qué lista era: exactamente el
    dato que la aplicación existe para conservar.

    409 Conflict y no 400: la petición está bien formada, lo que pasa es que
    choca con el estado actual del recurso. Y no 403, que hablaría de permisos.

    Deja al usuario la salida: borrar antes esas sesiones, o quedarse el mazo.
    Borrarlas en cascada sería decidir por él lo más destructivo.
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
    """Cambia el nombre o los iconos de un mazo ya creado.

    PATCH y no PUT porque se manda un cambio parcial, no el recurso entero. Es la
    diferencia semántica entre los dos verbos, y aquí importa: un PUT obligaría a
    reenviar el mazo completo solo para cambiar un icono.
    """
    deck = await _load_deck(deck_id)
    await deck_repository.update_deck(deck["_id"], payload)
    return await get_deck(deck_id)


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
    tag: str | None = Query(default=None, description="Filtra por etiqueta de sesión"),
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
            date_from=date_from, date_to=date_to, session_type=session_type, tag=tag
        ),
        sessions_counted=raw["sessions"],
        overall=overall,
        by_version=by_version,
        by_archetype=[linea(r, r["_id"]) for r in raw["by_archetype"]],
        by_session_type=[linea(r, r["_id"]) for r in raw["by_session_type"]],
    )
