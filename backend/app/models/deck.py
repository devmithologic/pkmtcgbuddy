"""Deck and deck version models.

The project's central idea lives here: a deck is not a list of cards, it is a
list *plus a history*. Every change produces a DeckVersion, and games will be
attributed to the version played, not just to the deck.

Rule that governs the design: **the current version is editable; earlier ones
stay frozen.** If v1 could change after games had been played with it, the
statistics attributed to v1 would become a lie. Creating a new version is the
gesture of preserving history before touching anything.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from app.models.card import CardSummary, DeckFormat
from app.models.pokemon import PokemonRef, PokemonRefOut

# Format rules. They go here, named, and not as loose numbers inside
# validation: when someone asks "why 4?", the name answers.
DECK_SIZE = 60
MAX_COPIES_PER_NAME = 4
MAX_ACE_SPEC = 1


class DeckCard(BaseModel):
    """A decklist entry: which card and how many copies.

    Stores only the id. Name, rarity and legality live in the `cards`
    collection and are resolved when validating. Duplicating them here
    would mean a resync could leave decks with stale data.
    """

    card_id: str
    quantity: int = Field(ge=1, le=60)


class DeckCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    deck_format: DeckFormat
    # The two Pokémon that identify the deck: "Dragapult / Dusknoir".
    # Optional because not every archetype reduces to a creature, and
    # because when creating the deck you may not have decided yet.
    primary_pokemon: PokemonRef | None = None
    secondary_pokemon: PokemonRef | None = None
    folder_id: str | None = None


class DeckUpdate(BaseModel):
    """Changes to an already-created deck: name and icons.

    Everything optional because it is a PATCH: only what changes is sent.
    Distinguishing "don't send it" from "set it to null" is not possible
    with a single optional field, so clearing an icon is done by sending
    the whole object without it.
    """

    name: str | None = Field(default=None, min_length=1, max_length=80)
    primary_pokemon: PokemonRef | None = None
    secondary_pokemon: PokemonRef | None = None
    # None here DOES mean something: "take it out of its folder". As in
    # FolderUpdate and unlike `name`, it is distinguished with exclude_unset.
    folder_id: str | None = None
    # Changing the format does NOT touch the cards: DeckValidation is
    # computed on read, so the decklist revalidates itself and the panel
    # will say what stopped being legal.
    # That is correct: an illegal deck is still saved and reported as such.
    deck_format: DeckFormat | None = None


class DeckImport(BaseModel):
    """A decklist in the PTCG Live text format."""

    text: str = Field(min_length=1)
    name: str | None = Field(default=None, min_length=1, max_length=80)
    folder_id: str | None = None


class DeckImportResult(BaseModel):
    """The created deck and what could not be resolved.

    `unresolved` is ALWAYS present, even when empty. That is the
    difference between importing and trusting: whoever pastes a 60-card
    list has the right to know whether 60 or 57 made it in, and which ones
    are missing, written exactly as they sent them.
    """

    deck: "DeckOut"
    imported_cards: int
    unresolved: list[str] = Field(default_factory=list)


class NewVersionRequest(BaseModel):
    """Message describing the change, like a commit's."""

    message: str = Field(min_length=1, max_length=200)


class DeckCardsUpdate(BaseModel):
    """Replaces the entire decklist of the current version.

    The complete list is sent instead of "add one Iono" on purpose: a PUT
    with the full state is *idempotent*, so repeating it duplicates
    nothing, and it avoids the concurrency problems of an incremental
    counter.
    """

    cards: list[DeckCard]


class ViolationCode(str, Enum):
    """Reasons a deck is not legal.

    A code alongside the message so the frontend can decide how to present
    it without parsing Spanish text.
    """

    WRONG_SIZE = "wrong_size"
    TOO_MANY_COPIES = "too_many_copies"
    TOO_MANY_ACE_SPEC = "too_many_ace_spec"
    ILLEGAL_IN_FORMAT = "illegal_in_format"
    UNKNOWN_CARD = "unknown_card"


class Violation(BaseModel):
    code: ViolationCode
    message: str
    # Cards involved, so the UI can point them out.
    card_ids: list[str] = Field(default_factory=list)


class DeckValidation(BaseModel):
    """Legality state of a decklist.

    NOT stored in the database. Computed on read, same as Matchup: it is a
    derived value, and storing it opens the door to it contradicting the
    decklist it describes.
    """

    is_legal: bool
    total_cards: int
    violations: list[Violation] = Field(default_factory=list)


class DeckVersionSummary(BaseModel):
    """An entry in the history, without the decklist."""

    id: str
    version: int
    message: str
    total_cards: int
    created_at: datetime


class DeckVersionOut(DeckVersionSummary):
    """A version with its decklist resolved.

    `cards` carries the full card —not just the id— because whoever renders
    the list needs the name and image, and resolving them on the client
    would be one request per card. See log_mentor/08.
    """

    cards: list["DeckCardOut"]


class DeckCardOut(BaseModel):
    quantity: int
    card: CardSummary
    # Data the UI needs to group and warn, already resolved.
    category: str
    is_ace_spec: bool
    is_basic_energy: bool
    legal_in_format: bool


class DeckSummary(BaseModel):
    """A deck in the listing: just enough to decide which one to open."""

    id: str
    name: str
    deck_format: DeckFormat
    current_version: int
    # The id in addition to the number: whoever logs a game needs to store
    # WHICH version it is attributed to, and the number alone does not
    # identify the document.
    current_version_id: str
    total_cards: int
    is_legal: bool
    updated_at: datetime
    # Out and not plain PokemonRef: this is a response, so it carries the
    # computed URLs. The input models above stick with PokemonRef, which is
    # what gets stored.
    primary_pokemon: PokemonRefOut | None = None
    secondary_pokemon: PokemonRefOut | None = None
    folder_id: str | None = None


class DeckOut(BaseModel):
    """An open deck: header, current version and its validation."""

    id: str
    name: str
    deck_format: DeckFormat
    current_version: DeckVersionOut
    validation: DeckValidation
    created_at: datetime
    updated_at: datetime
    primary_pokemon: PokemonRefOut | None = None
    secondary_pokemon: PokemonRefOut | None = None
    folder_id: str | None = None
