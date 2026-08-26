# MongoDB Denormalization for Sorting

> **Stack:** MongoDB · **Introduced in:** Card search rankings by release date and rarity · **Date:** 2026-08-15

## Definition

**Denormalization** is storing a copy of data from one collection in another so that queries on the second collection can use it for filtering or sorting without joining collections. The copy is recalculated and rewritten whenever the source changes; the trade-off is storage and synchronization cost against query performance.

## Why it exists

MongoDB has no native join. The `$lookup` aggregation stage exists, but it cannot participate in index-based sorting — a query with `$lookup` followed by `.sort()` will load all matching documents into memory and order them there, with a hard limit of 32 MB. If your result set exceeds that limit, the query fails.

For searchable fields that need ordering, two options exist:

1. Accept in-memory sorting and its 32 MB ceiling
2. Copy the field you need to order by into the document being ordered

Option 2 is denormalization. It is not elegant, but it is how indexes work: they order B-tree nodes by the fields that physically exist in the document.

## How it works

When a field arrives from another collection:

1. **At write time (or sync time):** Fetch the source value, calculate the derived field, write it into the document alongside the denormalized copy. For batch jobs, accumulate the updates and write them in bulk to avoid N network round trips.
2. **On read:** The field is already there. Indexes can order by it. Queries are fast.
3. **On source change:** Recalculate and rewrite. This cost is paid only when the source actually changes, not on every query.

The key insight: **denormalization is valid only when the source is stable.** Public metadata (a set's release date, a card's type) does not change. A user's name, balance, or location changes frequently, and denormalizing it would silently lose edits. The stability of the data decides whether denormalization is safe.

## In this project

**The problem:** The search found 32 results for "metal", but the first was a secret rare `Basic Metal Energy` (golden, high rarity). The 26 normal `Metal Energy` reprints were scattered through positions 8–32, ordered by id, starting from 1999. Users wanted the normal one first.

The normal and secret versions are the same card. Ordering by `name_lower` alone would not help — TCGdex calls them `"Metal Energy"` and `"Basic Metal Energy"`, so the secret always wins alphabetically. A better sort order needs:

1. Group them by identity (strip the "Basic" prefix)
2. Within each group, normal printings first
3. Within normality, newer first

All three pieces of information — the stripped name, whether it's a secret, and the set's release date — are needed in the sort key. The third lives in another collection (`sets`).

**Solution:** Copy `set_release_date` from `sets` into each `cards` document when the sets sync.

```python
# backend/app/db/set_repository.py
async def release_dates() -> dict[str, str]:
    """{set_id: "YYYY-MM-DD"}, for sorting reprints by age."""
    cursor = _collection().find({"release_date": {"$ne": None}}, {"release_date": 1})
    return {doc["_id"]: doc["release_date"] async for doc in cursor}


# backend/app/services/card_sync.py
def _stamp_set_dates(documents: list[dict], dates: dict[str, str]) -> int:
    """Copy the set's date into each card. Return count of cards left undated."""
    sin_fecha = 0
    for doc in documents:
        fecha = dates.get(card_repository.set_id_of(doc["_id"]))
        doc["set_release_date"] = fecha
        if not fecha:
            sin_fecha += 1
    return sin_fecha


# In the sync flow:
dates = await set_repository.release_dates()
_stamp_set_dates(documents, dates)
await _write(documents)
```

The denormalized field is then indexed and used in sort:

```python
# backend/app/db/card_repository.py - index creation
await collection.create_index(
    [
        ("sort_name", ASCENDING),
        ("printing_rank", ASCENDING),
        ("set_release_date", DESCENDING),  # denormalized from sets
        ("_id", ASCENDING),
    ]
)

# In search_cards():
.sort(
    [
        ("sort_name", ASCENDING),
        ("printing_rank", ASCENDING),
        ("set_release_date", DESCENDING),
        ("_id", ASCENDING),
    ]
)
```

## Gotchas

**Stale data:** If the source value changes, the denormalized copy does not update itself. A set's release date is immutable (it is history), so this is safe. But if you denormalize a user's name or a product's price, you must have a strategy to propagate the change — or accept that old documents will reflect old data. Never denormalize data that changes in production without an update plan.

**Storage cost:** Each copy takes disk space. With 15,021 cards and a string like `"2025-09-25"`, the overhead is small (10 bytes per document × 15,000 ≈ 150 KB). At scale (millions of documents), the math changes, and you must measure.

**Sync failures lose data:** If the sync that writes the denormalized field crashes halfway, documents are left inconsistent. The batch job approach (accumulate, write in bulk) is safer than document-at-a-time writes, but even bulk operations can fail. On failure, the solution here is to re-run; a second execution continues and completes without losing intermediate results.

**Schema migration:** Adding the denormalized field is not a breaking change (missing fields in MongoDB default to absent, which sorts to the end). But removing it requires a migration to drop the field from all documents, or the old field will interfere with new indexes.

## Related concepts

The inverse of this pattern: **deriving at read time instead of storing derived data.** See `log_mentor/` for how Pokémon sprites compute URLs from stable ids rather than storing them. The decision between the two depends on query volume (derivation costs per query; denormalization costs per write) and on whether the source is stable enough to denormalize safely.

See also [`12_MONGODB_PAGINATION_TOTAL_ORDER.md`](./12_MONGODB_PAGINATION_TOTAL_ORDER.md) — why sort keys must be unique to avoid duplicates across pages.

## References

- [MongoDB: Denormalization](https://www.mongodb.com/docs/manual/core/data-modeling-introduction/#data-modeling-patterns) — Patterns and tradeoffs in MongoDB data design
- [MongoDB Manual: Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/) — How indexes store and use multiple fields
- [MongoDB Manual: Sort Specification](https://www.mongodb.com/docs/manual/reference/method/cursor.sort/) — How `.sort()` uses indexes
