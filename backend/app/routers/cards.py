"""Endpoints for the /api/cards resource.

Reads from OUR MongoDB collection, not from TCGdex. The catalogue is filled by
`python -m app.services.card_sync`, a batch job run by hand.

The live proxy came first, on purpose: understand the direct call before
adopting the cache. On August 9, 2026 TCGdex was down for several hours and the
search stopped existing even though our server and our database were intact.
That settled the discussion.

Visible consequence: card_source no longer appears here. The adapter is still
the only thing that talks to TCGdex, but now the sync job is the one that calls
it, not the user's request.
"""

from fastapi import APIRouter, HTTPException, Query, status

from app.db import card_repository
from app.models.card import Card, CardCategory, CardSearchResult, DeckFormat

router = APIRouter(prefix="/cards", tags=["cards"])


@router.get("", response_model=CardSearchResult)
async def search_cards(
    # Query(...) declares query-string parameters with validation and documentation.
    # The short aliases are what the user sees in the URL: /api/cards?q=char
    q: str | None = Query(default=None, min_length=2, description="Part of the name"),
    format: DeckFormat | None = Query(default=None, description="Filter by legality"),
    category: CardCategory | None = Query(default=None),
    ace_spec: bool = Query(default=False, description="ACE SPEC cards only"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=24, ge=1, le=100),
) -> CardSearchResult:
    """Search cards from TCGdex.

    `min_length=2` on `q` is not a whim: a single letter returns thousands of
    results and punishes TCGdex without giving the user anything useful.
    """
    # There's no more 502 or 504 to handle: nothing outside gets called. The
    # only possible failures are our own database's, and those really are a
    # legitimate 500.
    result = await card_repository.search_cards(
        name=q,
        deck_format=format,
        category=category,
        ace_spec_only=ace_spec,
        page=page,
        page_size=page_size,
    )

    # Distinguishing "no matches" from "never synced" keeps an empty deployment
    # from looking like a search with no results.
    if not result.cards and await card_repository.count_cards() == 0:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "No cards are synced. Run:"
                " python -m app.services.card_sync"
            ),
        )

    return result


@router.get("/{card_id}", response_model=Card)
async def get_card(card_id: str) -> Card:
    """Card detail, with rarity, regulation mark and legality."""
    card = await card_repository.get_card(card_id)

    if card is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Card {card_id} is not in the synced catalogue",
        )

    return card
