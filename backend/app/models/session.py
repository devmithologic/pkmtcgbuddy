"""Modelos de sesión de juego.

Una **sesión** es un evento: una liga, una cup, una tarde de testing. Tiene una
fecha, un mazo, un tipo, y dentro sus rondas.

Sustituye al modelo anterior de partidas sueltas, que no se parecía a cómo se
juega: vas a un torneo y juegas cinco rondas seguidas con el mismo mazo el mismo
día. Registrarlas una a una obligaba a repetir fecha y mazo cinco veces, y perdía
el dato de que pertenecían al mismo evento.

Por eso `deck_version_id` vive aquí y no en la partida: el mazo se elige una vez
al empezar, no antes de cada ronda.

Las partidas van EMBEBIDAS en el documento de la sesión. El criterio que lo
decide —y que contradice a propósito lo que hicimos con los mazos— es la
dirección de las referencias: nada fuera de la sesión apunta a una partida
suelta. Con las versiones de mazo era al revés, la sesión sí apunta a una
versión, y por eso allí son colecciones separadas.

Además el array está acotado: un torneo son 4-9 rondas, nunca miles. Es el caso
que la documentación de MongoDB llama *one-to-few*.
"""

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field

from app.models.match import MatchResult
from app.models.pokemon import PokemonRef


class SessionType(str, Enum):
    """Tipo de evento.

    Enum en lugar de texto libre por lo mismo que MatchResult: FastAPI rechaza
    cualquier otro valor con un 422 automático, y las estadísticas de la fase 4
    necesitan que "cup" y "Cup" sean el mismo valor.
    """

    LEAGUE = "league"
    CUP = "cup"
    CHALLENGE = "challenge"
    ONLINE = "online"
    TESTING = "testing"


class MatchCreate(BaseModel):
    """Una ronda dentro de una sesión.

    Ya no lleva fecha ni mazo: los hereda de la sesión. Ese es justo el ahorro
    que justifica el cambio.
    """

    opponent_archetype: str = Field(min_length=1, max_length=100)
    result: MatchResult
    notes: str | None = Field(default=None, max_length=1000)

    # Los dos Pokémon del mazo rival. Van en la RONDA y no en la sesión porque en
    # un torneo de cinco rondas te enfrentas a cinco mazos distintos.
    #
    # Conviven con opponent_archetype en vez de sustituirlo: "Lost Box" se define
    # por Comfey y Sableye, y hay nombres de mazo que la gente usa y que no son
    # ninguna criatura.
    opponent_primary: PokemonRef | None = None
    opponent_secondary: PokemonRef | None = None


class MatchOut(MatchCreate):
    """Una ronda tal como se devuelve, con su número.

    `round` lo asigna el servidor al añadir. No es un identificador: las partidas
    embebidas no necesitan identidad propia porque nadie las referencia desde
    fuera. Es su posición en la sesión, y se renumera al borrar una.
    """

    round: int


class SessionCreate(BaseModel):
    played_at: date
    session_type: SessionType
    deck_version_id: str
    name: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=1000)


class SessionRecord(BaseModel):
    """El récord del evento: 3-1-1.

    Derivado al leer, nunca guardado — la misma regla que DeckValidation y que
    Matchup. Un contador almacenado puede acabar contradiciendo a las partidas
    que dice resumir.
    """

    wins: int
    losses: int
    ties: int

    @property
    def played(self) -> int:
        return self.wins + self.losses + self.ties


class SessionSummary(BaseModel):
    """Una sesión en el listado: lo justo para decidir cuál abrir."""

    id: str
    played_at: date
    session_type: SessionType
    name: str | None
    deck_name: str | None
    deck_version: int | None
    record: SessionRecord


class SessionOut(SessionSummary):
    """Una sesión abierta, con sus rondas."""

    deck_version_id: str
    notes: str | None
    matches: list[MatchOut]
    created_at: datetime


def compute_record(matches: list[dict]) -> SessionRecord:
    """Cuenta victorias, derrotas y empates."""
    return SessionRecord(
        wins=sum(1 for m in matches if m["result"] == MatchResult.WIN.value),
        losses=sum(1 for m in matches if m["result"] == MatchResult.LOSS.value),
        ties=sum(1 for m in matches if m["result"] == MatchResult.TIE.value),
    )
