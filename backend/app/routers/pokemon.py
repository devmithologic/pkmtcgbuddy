"""Pokémon search endpoint.

Read-only, and against our own collection: PokeAPI is never queried while
handling a request. Same decision as with cards, and for the same reason — on
August 9 TCGdex was down and the card search stopped existing.
"""

from fastapi import APIRouter, Query

from app.db import pokemon_repository
from app.models.pokemon import PokemonRefOut

router = APIRouter(prefix="/pokemon", tags=["pokemon"])


@router.get("", response_model=list[PokemonRefOut])
async def search_pokemon(
    q: str = Query(min_length=2, description="Part of the name"),
    limit: int = Query(default=20, ge=1, le=50),
) -> list[PokemonRefOut]:
    """Search Pokémon by name, by substring.

    min_length=2 for the same reason as the card search: a single letter
    returns hundreds of results and helps nobody.
    """
    return await pokemon_repository.search(q, limit=limit)
