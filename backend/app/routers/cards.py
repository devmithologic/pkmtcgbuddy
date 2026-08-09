"""Endpoints del recurso /api/cards.

Leen de NUESTRA colección de MongoDB, no de TCGdex. El catálogo se llena con
`python -m app.services.card_sync`, un trabajo por lotes que se ejecuta a mano.

El proxy en vivo fue lo primero, a propósito: entender la llamada directa antes
de adoptar la caché. El 9 de agosto de 2026 TCGdex estuvo caída varias horas y el
buscador dejó de existir aunque nuestro servidor y nuestra base estaban intactos.
Eso zanjó la discusión.

Consecuencia visible: card_source ya no aparece aquí. El adaptador sigue siendo el
único que habla con TCGdex, pero ahora quien lo llama es el job de sincronización,
no la petición del usuario.
"""

from fastapi import APIRouter, HTTPException, Query, status

from app.db import card_repository
from app.models.card import Card, CardCategory, CardSearchResult, DeckFormat

router = APIRouter(prefix="/cards", tags=["cards"])


@router.get("", response_model=CardSearchResult)
async def search_cards(
    # Query(...) declara parámetros de query string con validación y documentación.
    # Los alias cortos son los que verá el usuario en la URL: /api/cards?q=char
    q: str | None = Query(default=None, min_length=2, description="Parte del nombre"),
    format: DeckFormat | None = Query(default=None, description="Filtra por legalidad"),
    category: CardCategory | None = Query(default=None),
    ace_spec: bool = Query(default=False, description="Solo cartas ACE SPEC"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=24, ge=1, le=100),
) -> CardSearchResult:
    """Busca cartas en TCGdex.

    `min_length=2` en `q` no es capricho: una sola letra devuelve miles de
    resultados y castiga a TCGdex sin darle nada útil al usuario.
    """
    # Ya no hay 502 ni 504 que manejar: no se llama a nadie de fuera. Los únicos
    # fallos posibles son de nuestra base, y esos sí son un 500 legítimo.
    result = await card_repository.search_cards(
        name=q,
        deck_format=format,
        category=category,
        ace_spec_only=ace_spec,
        page=page,
        page_size=page_size,
    )

    # Distinguir "no hay coincidencias" de "nunca se sincronizó" evita que un
    # despliegue sin datos parezca una búsqueda sin resultados.
    if not result.cards and await card_repository.count_cards() == 0:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "No hay cartas sincronizadas. Ejecuta:"
                " python -m app.services.card_sync"
            ),
        )

    return result


@router.get("/{card_id}", response_model=Card)
async def get_card(card_id: str) -> Card:
    """Detalle de una carta, con rareza, marca de regulación y legalidad."""
    card = await card_repository.get_card(card_id)

    if card is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe la carta {card_id} en el catálogo sincronizado",
        )

    return card
