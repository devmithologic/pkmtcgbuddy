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

from pydantic import BaseModel, Field, field_validator

from app.models.match import MatchResult
from app.models.pokemon import PokemonRef, PokemonRefOut


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

    # Redeclarados, no heredados. MatchCreate los tiene como PokemonRef —lo que
    # entra y lo que se guarda— y aquí hace falta la variante con las URLs
    # calculadas. Una subclase puede estrechar el tipo de un campo heredado
    # siempre que el nuevo sea subtipo del anterior, y PokemonRefOut lo es.
    opponent_primary: PokemonRefOut | None = None
    opponent_secondary: PokemonRefOut | None = None


def normalize_tags(tags: list[str] | None) -> list[str]:
    """Recorta, pasa a minúsculas y quita duplicados, conservando el orden.

    Es lo único que impide que las etiquetas se degraden. Sin esto, "GameSmart",
    "gamesmart" y "  GameSmart " serían tres etiquetas distintas y el filtro
    dejaría de servir — el mismo problema que CLAUDE.md señala con los
    arquetipos escritos a mano.

    Se normaliza AL GUARDAR y no al leer: si se hiciera al leer, la base
    guardaría basura y cada consulta tendría que limpiarla otra vez.
    """
    if not tags:
        return []

    vistas: list[str] = []
    for bruto in tags:
        limpia = " ".join(bruto.strip().lower().split())
        if limpia and limpia not in vistas:
            vistas.append(limpia)
    return vistas


class SessionCreate(BaseModel):
    played_at: date
    session_type: SessionType
    deck_version_id: str
    name: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=1000)

    # Etiquetas libres para categorizar: la tienda, el propósito, lo que haga
    # falta. Varias por sesión porque "gamesmart" y "preparación regional" son
    # ejes distintos y no compiten entre sí.
    tags: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("tags")
    @classmethod
    def _normalizar(cls, v: list[str]) -> list[str]:
        # El validador va en el modelo, no en el router: así se aplica venga la
        # petición de donde venga, incluido el PATCH.
        return normalize_tags(v)


class SessionUpdate(BaseModel):
    """Correcciones sobre una sesión ya creada.

    Todo opcional porque es un PATCH: se manda solo lo que cambia, y
    exclude_unset distingue "no lo mandes" de "ponlo a null".

    Incluye deck_version_id a propósito. Equivocarse de mazo al registrar es
    fácil y hoy no había forma de arreglarlo — la sesión quedaba atribuida para
    siempre a un mazo que no jugaste, y con ella sus estadísticas.
    """

    played_at: date | None = None
    session_type: SessionType | None = None
    deck_version_id: str | None = None
    name: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=1000)
    tags: list[str] | None = Field(default=None, max_length=10)

    @field_validator("tags")
    @classmethod
    def _normalizar(cls, v: list[str] | None) -> list[str] | None:
        return normalize_tags(v) if v is not None else None


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
    # Los Pokémon DEL MAZO, no de la sesión: el prefijo deck_ los distingue,
    # igual que en deck_name y deck_version. Un mazo se reconoce antes por su
    # par de iconos que por su nombre escrito.
    #
    # PokemonRefOut y no PokemonRef: es una respuesta, así que las URLs se
    # calculan al leer y no hay nada nuevo que guardar.
    deck_primary: PokemonRefOut | None = None
    deck_secondary: PokemonRefOut | None = None
    record: SessionRecord
    tags: list[str] = Field(default_factory=list)


class TagCount(BaseModel):
    """Una etiqueta y cuántas sesiones la usan.

    El recuento es lo que hace útil la lista: distingue una etiqueta que usas de
    verdad de una que escribiste mal una vez.
    """

    tag: str
    sessions: int


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
