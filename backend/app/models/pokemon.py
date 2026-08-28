"""Reference to a Pokémon.

Used to visually identify a deck —yours or the opponent's— with one or two
icons, which is how tournament matchups are read at a glance.

It is not a card. A card is a specific printing with its set and its
rarity; this is the creature, and its national number is stable forever.
"""

from pydantic import BaseModel, computed_field

from app.services.pokemon_source import art_url, icon_url


class PokemonRef(BaseModel):
    """What gets stored and what gets accepted: the number and the name.
    Nothing else.

    Stores `dex_id` **and** `name` even though the name is derivable from
    the number. It is deliberate, bounded duplication:

    - The data is immutable. Dragapult will always be #887; there is no
      resync that could leave the name stale.
    - It avoids resolving 1351 names when reading a list of sessions.
      Without this, every round would need a lookup just to write its
      label.

    `sprite_url` used to live here too, with the same justification, and it
    **was wrong**. The URL is not immutable: it is a provider detail,
    exactly what `pokemon_source.py` exists to contain. By storing it, it
    got copied into every deck and every round, so the provider ended up
    leaking into the database and the promise that "switching providers is
    a one-line change" stopped being true: changing the constant would not
    have touched a single already-recorded round.

    It is the same rule already written for tags in CLAUDE.md, seen from
    the other side: store what the data cannot express, derive what it can.
    Old documents still carry their `sprite_url` key; Pydantic ignores
    fields it does not declare, so it sits there unused with no need to
    migrate anything.
    """

    dex_id: int
    name: str


class PokemonRefOut(PokemonRef):
    """What goes out through the API: what is stored, plus the two URLs
    computed on read.

    They live in a subclass and not in `PokemonRef` for a very concrete
    reason: `model_dump()` **includes** computed fields. Rounds are written
    with `**match.model_dump(mode="json")` in `session_repository`, so a
    computed_field on the input model would sneak the URLs back into Mongo
    through the back door — exactly the problem we are removing.

    Separating input and output is the DTO pattern the project already uses
    everywhere in Create/Out. Here it also acts as a physical barrier.

    Two URLs and not one because the two uses are incompatible: the HOME
    render weighs 124 KB and 20 search results would be 2.5 MB, while the
    1.2 KB sprite looks like a smudge at 56 pixels.
    """

    @computed_field
    @property
    def icon_url(self) -> str:
        """96×96 sprite. Dense lists: search, a session's rounds."""
        return icon_url(self.dex_id)

    @computed_field
    @property
    def art_url(self) -> str:
        """HOME render, 512×512. Deck header and deck listing."""
        return art_url(self.dex_id)
