"""Modelos de mazo y de versión de mazo.

La idea central del proyecto vive aquí: un mazo no es una lista de cartas, es una
lista *más un historial*. Cada cambio produce una DeckVersion, y las partidas se
atribuirán a la versión jugada, no solo al mazo.

Regla que gobierna el diseño: **la versión actual es editable; las anteriores
quedan congeladas.** Si la v1 pudiera cambiar después de haber jugado con ella,
las estadísticas atribuidas a la v1 pasarían a ser mentira. Crear una versión
nueva es el gesto de preservar el historial antes de tocar nada.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from app.models.card import CardSummary, DeckFormat

# Reglas del formato. Van aquí, con nombre, y no como números sueltos dentro de
# la validación: cuando alguien pregunte "¿por qué 4?", el nombre responde.
DECK_SIZE = 60
MAX_COPIES_PER_NAME = 4
MAX_ACE_SPEC = 1


class DeckCard(BaseModel):
    """Una entrada de la lista: qué carta y cuántas copias.

    Guarda solo el id. El nombre, la rareza y la legalidad viven en la colección
    `cards` y se resuelven al validar. Duplicarlos aquí significaría que una
    resincronización dejaría los mazos con datos viejos.
    """

    card_id: str
    quantity: int = Field(ge=1, le=60)


class DeckCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    deck_format: DeckFormat


class NewVersionRequest(BaseModel):
    """Mensaje que describe el cambio, como el de un commit."""

    message: str = Field(min_length=1, max_length=200)


class DeckCardsUpdate(BaseModel):
    """Reemplaza la lista entera de la versión actual.

    Se manda la lista completa en vez de "suma una Iono" a propósito: PUT con el
    estado completo es *idempotente*, así que repetirlo no duplica nada, y evita
    los problemas de concurrencia de un contador incremental.
    """

    cards: list[DeckCard]


class ViolationCode(str, Enum):
    """Motivos por los que un mazo no es legal.

    Un código además del mensaje para que el frontend pueda decidir cómo
    presentarlo sin analizar texto en español.
    """

    WRONG_SIZE = "wrong_size"
    TOO_MANY_COPIES = "too_many_copies"
    TOO_MANY_ACE_SPEC = "too_many_ace_spec"
    ILLEGAL_IN_FORMAT = "illegal_in_format"
    UNKNOWN_CARD = "unknown_card"


class Violation(BaseModel):
    code: ViolationCode
    message: str
    # Cartas implicadas, para que la interfaz pueda señalarlas.
    card_ids: list[str] = Field(default_factory=list)


class DeckValidation(BaseModel):
    """Estado de legalidad de una lista.

    NO se guarda en la base. Se calcula al leer, igual que Matchup: es un dato
    derivado, y almacenarlo abre la puerta a que contradiga a la lista que
    describe.
    """

    is_legal: bool
    total_cards: int
    violations: list[Violation] = Field(default_factory=list)


class DeckVersionSummary(BaseModel):
    """Una entrada del historial, sin la lista de cartas."""

    id: str
    version: int
    message: str
    total_cards: int
    created_at: datetime


class DeckVersionOut(DeckVersionSummary):
    """Una versión con su lista resuelta.

    `cards` lleva la carta completa —no solo el id— porque quien pinta la lista
    necesita nombre e imagen, y resolverlos en el cliente sería una petición por
    carta. Ver log_mentor/08.
    """

    cards: list["DeckCardOut"]


class DeckCardOut(BaseModel):
    quantity: int
    card: CardSummary
    # Datos que necesita la interfaz para agrupar y avisar, ya resueltos.
    category: str
    is_ace_spec: bool
    is_basic_energy: bool
    legal_in_format: bool


class DeckSummary(BaseModel):
    """Un mazo en el listado: lo justo para decidir cuál abrir."""

    id: str
    name: str
    deck_format: DeckFormat
    current_version: int
    # El id además del número: quien registra una partida necesita guardar A QUÉ
    # versión se atribuye, y el número por sí solo no identifica el documento.
    current_version_id: str
    total_cards: int
    is_legal: bool
    updated_at: datetime


class DeckOut(BaseModel):
    """Un mazo abierto: cabecera, versión actual y su validación."""

    id: str
    name: str
    deck_format: DeckFormat
    current_version: DeckVersionOut
    validation: DeckValidation
    created_at: datetime
    updated_at: datetime
