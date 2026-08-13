"""Endpoint de búsqueda de Pokémon.

Solo lectura y contra nuestra propia colección: PokeAPI no se consulta al atender
una petición. Es la misma decisión que con las cartas, y por el mismo motivo —el
9 de agosto TCGdex estuvo caída y el buscador de cartas dejó de existir.
"""

from fastapi import APIRouter, Query

from app.db import pokemon_repository
from app.models.pokemon import PokemonRef

router = APIRouter(prefix="/pokemon", tags=["pokemon"])


@router.get("", response_model=list[PokemonRef])
async def search_pokemon(
    q: str = Query(min_length=2, description="Parte del nombre"),
    limit: int = Query(default=20, ge=1, le=50),
) -> list[PokemonRef]:
    """Busca Pokémon por nombre, por subcadena.

    min_length=2 por lo mismo que en el buscador de cartas: una sola letra
    devuelve cientos de resultados y no ayuda a nadie.
    """
    return await pokemon_repository.search(q, limit=limit)
