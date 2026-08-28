"""Our card model.

This is NOT the shape TCGdex returns. It is the shape this application needs,
and the difference is deliberate: the rest of the code depends on these
models, never on the provider's JSON.

The pattern is called an *anti-corruption layer* — a layer that stops an
external system's model from leaking into your own. See services/card_source.py,
which is where the translation happens.

Concrete example of why it matters: TCGdex encodes that a card is ACE SPEC
inside the `rarity` field, with the literal "ACE SPEC Rare". Our domain
doesn't want a magic string scattered across the code; it wants a boolean
`is_ace_spec`. If TCGdex renames that rarity tomorrow, one file changes.
"""

from enum import Enum

from pydantic import BaseModel


class CardCategory(str, Enum):
    """The three card categories. Values taken from GET /v2/en/categories."""

    POKEMON = "Pokemon"
    TRAINER = "Trainer"
    ENERGY = "Energy"


class DeckFormat(str, Enum):
    """Tournament formats the application supports.

    Lives here, not in the deck module, because legality is a property of
    the card: the format only makes sense as a filter over cards.
    """

    STANDARD = "standard"
    EXPANDED = "expanded"


class CardSummary(BaseModel):
    """What a search returns.

    It is what TCGdex's listing gives: id, name and image. Deliberately
    thin — see the note on N+1 in services/card_source.py.
    """

    id: str
    name: str
    image_url: str | None = None


class Card(CardSummary):
    """A card with the detail the deck builder needs."""

    category: CardCategory
    rarity: str | None = None
    regulation_mark: str | None = None
    legal_standard: bool
    legal_expanded: bool

    # Derived, not copied: TCGdex expresses it as rarity == "ACE SPEC Rare".
    is_ace_spec: bool

    # Fingerprint of WHICH card this is, shared by all its reprints. The
    # adapter computes it from the name and the text; not from the set or
    # the rarity.
    #
    # It serves the reprint rule: if Boss's Orders is reprinted in a legal
    # set, older printings of the same text also become playable, and
    # TCGdex does not model that. See services/card_sync.py.
    identity: str = ""

    # Also derived, and with a vocabulary translation along the way: TCGdex
    # calls "Normal" what the rulebook calls *basic* energy. We store the
    # domain's term, not the provider's.
    #
    # It matters because the "max 4 copies per name" rule exempts exactly
    # basic energy: a deck can carry twenty Lightning Energy.
    is_basic_energy: bool = False

    def is_legal_in(self, deck_format: DeckFormat) -> bool:
        """Domain rule, not provider data. Deck validation will use it in
        the next slice."""
        return {
            DeckFormat.STANDARD: self.legal_standard,
            DeckFormat.EXPANDED: self.legal_expanded,
        }[deck_format]


class CardSearchResult(BaseModel):
    """A page of results.

    We return the page wrapped in an object instead of a bare array because
    the client needs to know which page it is on to be able to ask for the
    next one. An array has nowhere to hang that information.

    It does not include the total result count: TCGdex does not give it
    without downloading the entire collection, and lying with a made-up
    number would be worse than omitting it.
    """

    cards: list[CardSummary]
    page: int
    page_size: int
    has_more: bool
