# The N+1 Query Problem

> **Stack:** HTTP · **Introduced in:** card search — deciding what a result row shows · **Date:** 2026-08-08

## Definition

**N+1** is the access pattern where fetching a list of N items costs one query for the list plus one
query per item — N+1 round trips — because the list query does not return everything the caller needs.

## Why it matters

The pattern is easy to write and invisible in development. It appears when a loop contains a query:

```python
items = await fetch_list()                    # 1 request
for item in items:
    detail = await fetch_detail(item.id)      # N requests
```

With ten items on a local database this costs milliseconds and nobody notices. With twenty-four items
against a third-party API at 150 ms each, it is 3.6 seconds — and the cost scales with a number
chosen by the user, not by you. That is the property that makes it dangerous: adding a filter that
returns more rows turns a fast page into a broken one, with no code change.

The name comes from ORMs, where lazy-loading a relation inside a loop silently emits a query per row.
The shape is the same wherever a list is enriched item by item: SQL, HTTP, GraphQL resolvers, gRPC.

## How it works

The fix is always one of three moves:

1. **Make the list query return more.** Best when the API supports it — one round trip, done.
2. **Batch the detail queries.** One request for N ids (`WHERE id IN (...)`, or a batch endpoint)
   turns N+1 into 2.
3. **Defer the detail until it is actually needed.** If most users never look at most rows, fetching
   detail for all of them was wasted work regardless of how it was batched.

Which one applies depends on what the upstream offers, which is why the decision belongs in the
adapter rather than in a component.

## In this project

TCGdex forces the issue. Its list endpoint returns only four fields:

```
GET /v2/en/cards?name=pikachu&legal.standard=true
[{"id": "sv05-051", "localId": "51", "name": "Pikachu", "image": "..."}, ...]
```

No `rarity`, no `legal`, no `regulationMark` — even though the API *filters* on those fields. Getting
them means one call per card:

```
GET /v2/en/cards/sv05-051     ~150 ms each
```

Option 1 is unavailable: the API decides what the list returns. Option 2 is unavailable: there is no
batch endpoint. So this project takes option 3.

```python
# backend/app/services/card_source.py
async def search_cards(...) -> CardSearchResult:
    """Returns CardSummary: id, name, image. One request."""

async def get_card(card_id: str) -> Card | None:
    """Full detail. One request, on demand."""
```

The consequence is visible in the interface, and that is the point:

```jsx
// frontend/src/components/CardSearch.jsx — grid shows name + image only
{results.map((card) => <button onClick={() => setSelectedId(card.id)}>…</button>)}

// frontend/src/components/CardDetail.jsx — one request, when a card is chosen
useEffect(() => { getCard(cardId, controller.signal).then(setCard) }, [cardId])
```

Twenty-four results cost **one** request. Opening a card costs **one more**. The user who scans a page
and picks nothing pays for one call instead of twenty-five.

Note what was given up: rarity and legality are not visible in the grid. That is a real cost, chosen
knowingly. Showing a legality badge on every result would mean 24 extra requests for information most
users would not read — and the honest alternative, if it were ever required, is to pre-fetch card data
into MongoDB, which is the moment caching stops being premature.

## Gotchas

- **It hides inside helper functions.** `for card in cards: enrich(card)` looks like local work. The
  request is one call deeper. Reading a query count, not code, is what finds these.
- **Development data is too small to reveal it.** Three rows never hurt. Test with realistic volume,
  or count queries in a test.
- **`asyncio.gather` reduces latency, not load.** Firing N requests concurrently makes the page
  faster while hitting the upstream just as hard — and is a good way to earn a rate limit.
- **Pagination limits the damage but does not remove it.** N+1 with a page size of 24 is 25 requests
  per page, every page.
- **The inverse mistake exists too.** Fetching full detail for a list nobody expands is wasted work in
  the other direction.

## Related concepts

`see 07_PYTHON_ADAPTER_PATTERN.md` — the module where this decision lives; eager vs. lazy loading;
DataLoader-style request batching; caching, which changes the arithmetic rather than the pattern.

## References

- [Web performance: understanding latency — MDN](https://developer.mozilla.org/en-US/docs/Web/Performance/Guides/Understanding_latency) — why round trips, not payload size, dominate
- [SELECT N+1 problem — Hibernate Community Docs](https://docs.jboss.org/hibernate/orm/6.4/introduction/html_single/Hibernate_Introduction.html#association-fetching) — the canonical ORM description of the same pattern
