"""Statistics models.

None of this is stored. Everything is computed on read, aggregating over
`sessions`. It is the same rule as a session's record and as DeckValidation,
and here it matters even more: a stored win rate goes stale the moment you
correct a mislogged round, and nobody notices.
"""

from datetime import date

from pydantic import BaseModel, computed_field

from app.models.session import SessionType


class StatLine(BaseModel):
    """A statistics row: wins, losses, ties and their percentage.

    `win_rate` is computed over the TOTAL games played, ties included. It
    is a debatable decision —many trackers discard ties, and some count
    them as half a win— so the three numbers are returned separately so
    the UI can show "18-7-2" alongside the percentage. A percentage without
    its record next to it hides how many games are behind it, and 100% of
    2 games is not the same as 67% of 30.
    """

    label: str
    wins: int
    losses: int
    ties: int

    # @computed_field makes Pydantic include the property in the JSON and
    # in the OpenAPI schema. Without it, a plain @property exists in Python
    # but does not appear in the response: the client would receive only
    # the three counters and would have to recompute, which is exactly the
    # duplication this avoids.
    @computed_field
    @property
    def played(self) -> int:
        return self.wins + self.losses + self.ties

    @computed_field
    @property
    def win_rate(self) -> float:
        """Over the total played, ties included. See the class note."""
        return round(self.wins / self.played, 4) if self.played else 0.0


class VersionStatLine(StatLine):
    """Like StatLine, but identifying the deck version.

    This is THE row of the project: comparing v1 to v2 is the question no
    commercial tracker answers, and it is why versioning exists at all.
    """

    version: int
    version_id: str
    message: str


class StatsFilters(BaseModel):
    """Which slice was applied. Returned so the UI can display it and the
    user doesn't read a number thinking it is global."""

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
