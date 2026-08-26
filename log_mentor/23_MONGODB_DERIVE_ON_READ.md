# Derive on Read

> **Stack:** MongoDB · **Introduced in:** Sourcing images from reprints when the primary card has no image · **Date:** 2026-08-26

## Definition

**Image borrowing** is deriving a missing value at query time by finding a related document that has the value. Instead of storing a derived field, the application computes it on read: when a card has no image URL, query the database for reprints of the same card (by identity), pick the one with the best image (using a ranking criteria), and return its URL. The URL is computed and returned but not stored, so if a reprint's image later changes or a new reprint appears, the next query gets the new URL.

## Why it exists

TCGdex does not have images for 1,035 of our 15,021 synced cards. Among them is the entire set `sve` — all 24 current basic energy cards printed without artwork. These are a problem: show the user a card with no image and the search result looks broken.

But 566 of those 1,035 have reprints that *do* have images. A reprint is the same card: same text, same rules, same everything except the art. Taking the image from a reprint is a lie and truth at the same time — the image is not of *this* printing, but it is of *this* card.

**Two alternative approaches and why they were not taken:**

1. **Store the borrowed image.** Write `image_url` to the database with a reprint's URL. Downside: the URL is now data that "belongs" to another card. If that reprint's image changes or a better reprint appears, this document is out of sync. The data decays.

2. **Fetch live from the source.** When the API returns a card with no image, check TCGdex or a fallback provider. Downside: adds latency to every search, and doesn't solve the problem if TCGdex still has no image.

Image borrowing computes at read time: zero stored data to sync, one database query per *page* of results (not per *card*), and the image is always the most recent option.

## How it works

**Step 1: Collect missing images on a page**

When the API returns a page of search results, check which cards have no image:

```python
async def _borrowed_images(documents: list[dict]) -> dict[str, str]:
    """For cards with no image, find the best-image reprint."""
    # Collect all identities (content signatures) that need an image
    identidades = {
        doc["identity"]
        for doc in documents
        if not doc.get("image_url") and doc.get("identity")
    }
    if not identidades:
        return {}  # Nothing to do
```

**Step 2: Query for reprints of each missing identity**

Query the database once with all identities, get back the reprints that do have images:

```python
    # Fetch reprints that have images
    cursor = _collection().find(
        {"identity": {"$in": list(identidades)}, "image_url": {"$ne": None}},
        {"identity": 1, "image_url": 1, "printing_rank": 1, "set_release_date": 1},
    )
```

This is a single query for a page of results, not one per card. For a 20-card page with 3 missing images, it's one query returning ~15 reprints.

**Step 3: Select the best reprint for each identity**

Among the reprints of each card, pick the "best" one using the same ranking as the search interface:

```python
    mejor: dict[str, dict] = {}
    async for candidata in cursor:
        actual = mejor.get(candidata["identity"])
        if actual is None or _es_mejor_impresion(candidata, actual):
            mejor[candidata["identity"]] = candidata
    
    return {
        doc["_id"]: mejor[doc["identity"]]["image_url"]
        for doc in documents
        if not doc.get("image_url") and doc.get("identity") in mejor
    }
```

The tiebreaker is `_es_mejor_impresion()`: prefer normal over secret, new over old, and use id to break ties. This ensures deterministic behavior.

**Step 4: Return it without storing**

The map of `{card_id: borrowed_image_url}` is applied while the repository builds its response models, so the substitution never leaves the `db` layer and the stored document is never updated:

```python
# backend/app/db/card_repository.py, inside search_cards()
pagina = documents[:page_size]
prestadas = await _borrowed_images(pagina)

return CardSearchResult(
    cards=[
        CardSummary(
            id=doc["_id"],
            # ...
            image_url=doc.get("image_url") or prestadas.get(doc["_id"]),
        )
        for doc in pagina
    ],
    # ...
)
```

The routers know nothing about any of this: they receive a `CardSummary` that already carries a usable
URL. That is the dependency direction of this repo — `routers → services → db → models` — and putting
the substitution in the endpoint instead would have meant repeating it in every endpoint that returns
a card.

## In this project

**The measurement:** TCGdex measured against its API showed:
- 1,035 cards with no image
- 566 of them have a reprint with an image
- 469 cannot be fixed (no reprints at all, or all reprints are also imageless)

For the 566, image borrowing makes them displayable. The cost is one database query per page, which is negligible (the page already took multiple queries for search, sorting, and fetching the cards themselves).

**The actual implementation:**

```python
# backend/app/db/card_repository.py

def _es_mejor_impresion(candidata: dict, actual: dict) -> bool:
    """Ranking criteria: normal before secret, new before old."""
    rank_c = candidata.get("printing_rank", 0)
    rank_a = actual.get("printing_rank", 0)
    if rank_c != rank_a:
        return rank_c < rank_a  # Lower rank wins
    
    fecha_c = candidata.get("set_release_date") or ""
    fecha_a = actual.get("set_release_date") or ""
    if fecha_c != fecha_a:
        return fecha_c > fecha_a  # Newer date wins
    
    return candidata["_id"] < actual["_id"]  # Tiebreaker

async def _borrowed_images(documents: list[dict]) -> dict[str, str]:
    """{card_id: url} for cards without images, borrowed from reprints."""
    identidades = {
        doc["identity"]
        for doc in documents
        if not doc.get("image_url") and doc.get("identity")
    }
    if not identidades:
        return {}
    
    cursor = _collection().find(
        {"identity": {"$in": list(identidades)}, "image_url": {"$ne": None}},
        {"identity": 1, "image_url": 1, "printing_rank": 1, "set_release_date": 1},
    )
    
    mejor: dict[str, dict] = {}
    async for candidata in cursor:
        actual = mejor.get(candidata["identity"])
        if actual is None or _es_mejor_impresion(candidata, actual):
            mejor[candidata["identity"]] = candidata
    
    return {
        doc["_id"]: mejor[doc["identity"]]["image_url"]
        for doc in documents
        if not doc.get("image_url") and doc.get("identity") in mejor
    }
```

The borrowing happens inside the repository layer, not exposed to the router. This is a key architectural decision: keeping derivation low in the stack (`db` layer, not `routers`):

```python
# backend/app/db/card_repository.py

async def search_cards(...) -> CardSearchResult:
    # ... query documents ...
    pagina = documents[:page_size]
    prestadas = await _borrowed_images(pagina)
    # Apply borrowed images to summary cards before returning
    return CardSearchResult(cards=[...])

async def get_card(card_id: str) -> Card | None:
    document = await _collection().find_one({"_id": card_id})
    if not document:
        return None
    carta = card_from_document(document)
    if not carta.image_url:
        # Single-card lookup: borrow if needed
        carta.image_url = (await _borrowed_images([document])).get(card_id)
    return carta

async def get_cards_by_ids(card_ids: list[str]) -> dict[str, Card]:
    # ... query documents ...
    prestadas = await _borrowed_images(documents)
    # Build card dict with borrowed images applied
    cartas = {}
    for doc in documents:
        doc["image_url"] = prestadas.get(doc["_id"]) or doc.get("image_url")
        cartas[doc["_id"]] = card_from_document(doc)
    return cartas
```

**Why this pattern exists here:** The alternative (storing the URL) was rejected because TCGdex data is a moving target. New printings appear, old ones get corrected, images are resynced. Storing a derived value that belongs to another card couples the two cards at the database level — an update to the reprint does not automatically refresh the dependent. Deriving at read time keeps them decoupled. By deriving inside the repository, the router never sees the difference: all three query methods return cards with complete image URLs, whether original or borrowed.

## Gotchas

**Image borrowing only works if at least one reprint has an image.** The 469 cards where every reprint is also missing an image cannot be fixed this way. They still appear in search with `image_url: null`. A second-level fallback (placeholder image, Pokémon icon, set icon) would be handled at the UI layer.

**The ranking is the same as the search, but that's not required.** The function chooses "best" for the image, and it happens to use the same criteria as search ranking. This is not a law — image borrowing could prefer rare or special printings. But in practice, choosing the same-as-search result makes intuitive sense: if searching for Metal Energy offers you the normal printing first, the image should be of that one.

**Identity must exist.** The function filters to `doc.get("identity")`, so cards with no identity (a data quality issue) are skipped. If a card is malformed and has no `identity` field, it also has no reprints to borrow from, so this is correct behavior.

**Determinism requires the id tiebreaker.** Without the `_id` tiebreaker in `_es_mejor_impresion`, which reprint's image you get could depend on the order MongoDB returns results, and two queries could return different images. The id provides a stable sort order. This matters for tests and for user expectations: running the same search twice should show the same image.

## Related concepts

See [`22_MONGODB_SEPARATE_SORT_SEARCH_FIELDS.md`](./22_MONGODB_SEPARATE_SORT_SEARCH_FIELDS.md) — `printing_rank` is calculated the same way here and in the search sorting, creating a consistent user experience.

The `identity` field used to group reprints is calculated by `_identity()` in `backend/app/services/card_source.py:167` — it combines a card's name, text, and attack signatures to create a unique content fingerprint.

See [`18_MONGODB_DENORMALIZATION_FOR_SORTING.md`](./18_MONGODB_DENORMALIZATION_FOR_SORTING.md) — an inverse pattern: denormalization stores derived data at write time. Image borrowing computes it at read time. The choice between the two depends on query volume vs. source volatility.

## References

- [MongoDB: $in Operator](https://www.mongodb.com/docs/manual/reference/operator/query/in/) — Querying by a list of identities in a single operation
- [MongoDB: $ne Operator](https://www.mongodb.com/docs/manual/reference/operator/query/ne/) — Finding documents where a field is not null (or missing)
- [Database Design: Denormalization vs. Derivation](https://en.wikipedia.org/wiki/Denormalization) — When to store vs. compute derived data
