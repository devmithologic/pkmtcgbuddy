"""Modelos de estadísticas.

Nada de esto se guarda. Todo se calcula al leer, agregando sobre `sessions`.
Es la misma regla que el récord de una sesión y que DeckValidation, y aquí es más
importante todavía: un win rate almacenado se queda obsoleto en cuanto corriges
una ronda mal anotada, y nadie se entera.
"""

from datetime import date

from pydantic import BaseModel, computed_field

from app.models.session import SessionType


class StatLine(BaseModel):
    """Un renglón de estadística: victorias, derrotas, empates y su porcentaje.

    `win_rate` se calcula sobre el TOTAL de partidas jugadas, empates incluidos.
    Es una decisión discutible —muchos trackers descartan los empates, y algunos
    los cuentan como media victoria— así que se devuelven los tres números por
    separado para que la interfaz pueda mostrar «18-7-2» junto al porcentaje. Un
    porcentaje sin su récord al lado esconde cuántas partidas hay detrás, y 100%
    de 2 partidas no es lo mismo que 67% de 30.
    """

    label: str
    wins: int
    losses: int
    ties: int

    # @computed_field hace que Pydantic incluya la property en el JSON y en el
    # esquema de OpenAPI. Sin él, una @property normal existe en Python pero no
    # sale en la respuesta: el cliente recibiría solo los tres contadores y
    # tendría que recalcular, que es exactamente la duplicación que se evita.
    @computed_field
    @property
    def played(self) -> int:
        return self.wins + self.losses + self.ties

    @computed_field
    @property
    def win_rate(self) -> float:
        """Sobre el total jugado, empates incluidos. Ver la nota de la clase."""
        return round(self.wins / self.played, 4) if self.played else 0.0


class VersionStatLine(StatLine):
    """Como StatLine, pero identificando la versión del mazo.

    Es EL renglón del proyecto: comparar v1 con v2 es la pregunta que ningún
    tracker comercial responde y por la que existe todo el versionado.
    """

    version: int
    version_id: str
    message: str


class StatsFilters(BaseModel):
    """Qué recorte se aplicó. Se devuelve para que la interfaz pueda mostrarlo
    y el usuario no interprete un número creyendo que es global."""

    date_from: date | None = None
    date_to: date | None = None
    session_type: SessionType | None = None
    tag: str | None = None


class DeckStats(BaseModel):
    deck_id: str
    deck_name: str
    filters: StatsFilters
    sessions_counted: int
    overall: StatLine
    by_version: list[VersionStatLine]
    by_archetype: list[StatLine]
    by_session_type: list[StatLine]
