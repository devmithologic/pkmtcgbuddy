"""Game session models.

A **session** is an event: a league, a cup, a testing afternoon. It has a
date, a deck, a type, and its rounds inside.

It replaces the earlier model of standalone games, which did not resemble
how the game is actually played: you go to a tournament and play five
rounds in a row with the same deck on the same day. Logging them one by one
forced repeating the date and the deck five times, and lost the fact that
they belonged to the same event.

That is why `deck_version_id` lives here and not on the game: the deck is
chosen once at the start, not before every round.

Games are EMBEDDED in the session document. The criterion that decides
this —and that deliberately contradicts what we did with decks— is the
direction of the references: nothing outside the session points to a
standalone game. With deck versions it is the other way around, the
session does point to a version, and that is why those are separate
collections.

The array is also bounded: a tournament is 4-9 rounds, never thousands. It
is the case MongoDB's documentation calls *one-to-few*.
"""

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator

from app.models.match import MatchResult
from app.models.pokemon import PokemonRef, PokemonRefOut


class SessionType(str, Enum):
    """Event type.

    Enum instead of free text for the same reason as MatchResult: FastAPI
    rejects any other value with an automatic 422, and phase 4's
    statistics need "cup" and "Cup" to be the same value.
    """

    LEAGUE = "league"
    CUP = "cup"
    CHALLENGE = "challenge"
    ONLINE = "online"
    TESTING = "testing"


class MatchCreate(BaseModel):
    """A round within a session.

    No longer carries a date or a deck: it inherits them from the session.
    That is exactly the saving that justifies the change.
    """

    opponent_archetype: str = Field(min_length=1, max_length=100)
    result: MatchResult
    notes: str | None = Field(default=None, max_length=1000)

    # The opponent deck's two Pokémon. They live on the ROUND and not on the
    # session because in a five-round tournament you face five different
    # decks.
    #
    # They coexist with opponent_archetype instead of replacing it: "Lost
    # Box" is defined by Comfey and Sableye, and there are deck names people
    # use that are not any creature at all.
    opponent_primary: PokemonRef | None = None
    opponent_secondary: PokemonRef | None = None


class MatchOut(MatchCreate):
    """A round as it is returned, with its number.

    `round` is assigned by the server when adding it. It is not an
    identifier: embedded games don't need an identity of their own because
    nothing references them from outside. It is their position within the
    session, and it is renumbered when one is deleted.
    """

    round: int

    # Redeclared, not inherited. MatchCreate has them as PokemonRef —what
    # comes in and what gets stored— and here the variant with the computed
    # URLs is needed. A subclass can narrow the type of an inherited field
    # as long as the new one is a subtype of the old one, and PokemonRefOut
    # is.
    opponent_primary: PokemonRefOut | None = None
    opponent_secondary: PokemonRefOut | None = None


def normalize_tags(tags: list[str] | None) -> list[str]:
    """Trims, lowercases and removes duplicates, keeping order.

    It is the only thing that keeps tags from degrading. Without this,
    "GameSmart", "gamesmart" and "  GameSmart " would be three different
    tags and the filter would stop being useful — the same problem
    CLAUDE.md points out with hand-written archetypes.

    It is normalized ON SAVE and not on read: if it were done on read, the
    database would store garbage and every query would have to clean it up
    again.
    """
    if not tags:
        return []

    seen: list[str] = []
    for raw_tag in tags:
        cleaned = " ".join(raw_tag.strip().lower().split())
        if cleaned and cleaned not in seen:
            seen.append(cleaned)
    return seen


class SessionCreate(BaseModel):
    played_at: date
    session_type: SessionType
    deck_version_id: str
    name: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=1000)

    # Free-form tags for categorizing: the store, the purpose, whatever is
    # needed. Several per session because "gamesmart" and "regional prep"
    # are different axes and don't compete with each other.
    tags: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("tags")
    @classmethod
    def _normalize(cls, v: list[str]) -> list[str]:
        # The validator lives on the model, not the router: that way it
        # applies no matter where the request comes from, PATCH included.
        return normalize_tags(v)


class SessionUpdate(BaseModel):
    """Corrections to an already-created session.

    Everything optional because it is a PATCH: only what changes is sent,
    and exclude_unset distinguishes "don't send it" from "set it to null".

    Includes deck_version_id on purpose. Picking the wrong deck when
    logging is easy and until now there was no way to fix it — the session
    stayed attributed forever to a deck you didn't play, and its statistics
    with it.
    """

    played_at: date | None = None
    session_type: SessionType | None = None
    deck_version_id: str | None = None
    name: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=1000)
    tags: list[str] | None = Field(default=None, max_length=10)

    @field_validator("tags")
    @classmethod
    def _normalize(cls, v: list[str] | None) -> list[str] | None:
        return normalize_tags(v) if v is not None else None


class SessionRecord(BaseModel):
    """The event's record: 3-1-1.

    Derived on read, never stored — the same rule as DeckValidation and as
    Matchup. A stored counter can end up contradicting the games it claims
    to summarize.
    """

    wins: int
    losses: int
    ties: int

    @property
    def played(self) -> int:
        return self.wins + self.losses + self.ties


class SessionSummary(BaseModel):
    """A session in the listing: just enough to decide which one to open."""

    id: str
    played_at: date
    session_type: SessionType
    name: str | None
    deck_name: str | None
    deck_version: int | None
    # The DECK's Pokémon, not the session's: the deck_ prefix distinguishes
    # them, same as in deck_name and deck_version. A deck is recognized
    # sooner by its pair of icons than by its written name.
    #
    # PokemonRefOut and not PokemonRef: this is a response, so the URLs are
    # computed on read and there is nothing new to store.
    deck_primary: PokemonRefOut | None = None
    deck_secondary: PokemonRefOut | None = None
    record: SessionRecord
    tags: list[str] = Field(default_factory=list)


class TagCount(BaseModel):
    """A tag and how many sessions use it.

    The count is what makes the list useful: it distinguishes a tag you
    actually use from one you mistyped once.
    """

    tag: str
    sessions: int


class SessionOut(SessionSummary):
    """An open session, with its rounds."""

    deck_version_id: str
    notes: str | None
    matches: list[MatchOut]
    created_at: datetime


def compute_record(matches: list[dict]) -> SessionRecord:
    """Counts wins, losses and ties."""
    return SessionRecord(
        wins=sum(1 for m in matches if m["result"] == MatchResult.WIN.value),
        losses=sum(1 for m in matches if m["result"] == MatchResult.LOSS.value),
        ties=sum(1 for m in matches if m["result"] == MatchResult.TIE.value),
    )
