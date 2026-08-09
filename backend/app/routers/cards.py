"""Endpoints del recurso /api/cards.

Estas rutas no tocan MongoDB: son un proxy sobre TCGdex. Las cartas no son datos
nuestros, así que no los guardamos todavía. Cuando la latencia de ~500ms moleste,
la caché será una decisión consciente y no una suposición inicial.
"""

import httpx
from fastapi import APIRouter, HTTPException, Query, status

from app.models.card import Card, CardCategory, CardSearchResult, DeckFormat
from app.services import card_source
from app.services.card_source import CardSourceError

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
    try:
        return await card_source.search_cards(
            name=q,
            deck_format=format,
            category=category,
            ace_spec_only=ace_spec,
            page=page,
            page_size=page_size,
        )
    except httpx.TimeoutException:
        # 504 Gateway Timeout: nosotros estamos bien, el servicio del que
        # dependemos no contestó. Un 500 diría que el fallo es nuestro.
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="TCGdex tardó demasiado en responder. Inténtalo de nuevo.",
        )
    except (httpx.HTTPError, CardSourceError):
        # 502 Bad Gateway: recibimos algo, pero no era utilizable. Cubre tanto el
        # fallo de transporte (httpx) como el de contenido (CardSourceError): un
        # 200 con HTML, un campo que desapareció, una categoría nueva. Sin el
        # segundo, esos casos serían un 500 y culparían a nuestro servidor.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No se pudo consultar TCGdex.",
        )


@router.get("/{card_id}", response_model=Card)
async def get_card(card_id: str) -> Card:
    """Detalle de una carta, con rareza, marca de regulación y legalidad."""
    try:
        card = await card_source.get_card(card_id)
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="TCGdex tardó demasiado en responder.",
        )
    except (httpx.HTTPError, CardSourceError):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="No se pudo consultar TCGdex."
        )

    if card is None:
        # 404 nuestro, porque el recurso que el cliente pidió no existe. Distinto
        # de un 502: ahí el problema sería del intermediario, no de la petición.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"No existe la carta {card_id}"
        )

    return card
