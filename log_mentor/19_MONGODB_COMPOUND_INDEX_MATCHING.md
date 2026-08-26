# MongoDB Compound Index Field and Direction Matching

> **Stack:** MongoDB · **Introduced in:** Fixing card search order with composite sort keys · **Date:** 2026-08-15

## Definition

A **compound index** is an index on multiple fields. When MongoDB executes a query with a `.sort()` clause, it will use a compound index to order results *only if the index fields and sort directions match exactly, field by field*. If they do not match, MongoDB loads all matching documents into memory and sorts them there, consuming both CPU and a 32 MB heap limit.

## Why it exists

The mechanism is a B-tree: a sorted tree where each node is ordered by its first key, then subdivided by the second key, and so on. The order of fields in the index is baked into the structure. Asking the B-tree to produce results ordered by fields in a different sequence or in opposite directions is asking it to traverse itself backwards and sideways — which it cannot do efficiently. So MongoDB falls back to in-memory sort.

This creates a **silent performance cliff:** a query that works with a small result set fails (times out, returns "sort exceeded limit") as the set grows. The error message names the 32 MB memory limit, but the root cause is that the index was never used for the sort in the first place.

## How it works

**B-tree structure:** Imagine a compound index on `(name, age)` in ascending order.

```
                    ┌─────────────┐
                    │   Root      │
                    └─────────────┘
                          │
            ┌─────────────┬┴─┬──────────────┐
        ┌───▼──┐      ┌──▼──┐          ┌──▼──┐
        │ A-M  │      │ N-S  │         │ T-Z  │
        └──────┘      └──────┘         └──────┘
            │             │                │
        ┌───┼─┬──┐    ┌───┼─┬──┐      ┌───┼─┬──┐
      age: age: age: age: age: age:  age: age: age:
      20  45  60  22  50  70  25  55  80
```

Queries ordered by `(name ASC, age ASC)` traverse this structure top-to-bottom, left-to-right, and the results come out pre-sorted. But a query sorted by `(age ASC, name ASC)` would need to traverse sideways through age subdivisions, which the B-tree does not support. So MongoDB scans the index for matching documents, loads them into memory, and re-sorts them.

**The rule:** Each of these must match **exactly**:

1. The fields in the index
2. The order of those fields
3. The sort direction (ascending vs. descending) of each field

A `.sort([("name", 1), ("age", 1)])` will use an index on `{name: 1, age: 1}` but not one on `{name: 1, age: -1}` or `{age: 1, name: 1}`.

## In this project

**The problem:** Card search needed to order by four fields — a stripped name, rarity rank (normal before secret), set release date (new before old), and id (tiebreaker). No existing index had all four, in that order, with those directions.

**The solution:**

```python
# backend/app/db/card_repository.py

# Index definition - EXACTLY matches the sort order
await collection.create_index(
    [
        ("sort_name", ASCENDING),        # 1
        ("printing_rank", ASCENDING),    # 2
        ("set_release_date", DESCENDING),# 3 — descending, not ascending
        ("_id", ASCENDING),              # 4
    ]
)

# Query - MUST use the same order and directions
cursor = (
    _collection()
    .find(query)
    .sort(
        [
            ("sort_name", ASCENDING),
            ("printing_rank", ASCENDING),
            ("set_release_date", DESCENDING),
            ("_id", ASCENDING),
        ]
    )
    .skip(skip)
    .limit(page_size + 1)
)
```

The third field deliberately uses descending order: among reprints of the same card with the same rarity, the most recent (latest date) should come first. Changing one direction without changing the index would silently stop using the index, and queries would degrade as the result set grows.

**How to verify:** MongoDB's query planner can be inspected with `.explain()`:

```javascript
db.cards.find({...}).sort([...]).explain("executionStats")
```

Look for:
- `executionStats.executionStages.stage === "COLLSCAN"` → no index used, or index used only for filtering
- `executionStats.executionStages.stage === "SORT"` → index was used to filter, but MongoDB is sorting in memory
- `executionStats.executionStages.stage === "IXSCAN"` (with no subsequent `SORT`) → index was used for both filtering and sorting (ideal)

## Gotchas

**Direction matters, even when it looks wrong.** If you sort by descending date but create an ascending index, the query will still work — it will just load everything into memory and reverse it there. For a search result set, this feels okay at 10 results, but at 10,000 it fails with "executor error: aggregation returned too many results to sort." The query never told you the index was not helping; the error came from the sort's memory limit, blaming the dataset when the real problem was the index mismatch.

**Index reordering is not free.** Changing the order of fields in an index breaks sort performance for old queries using the old order. If you have two queries sorting by `(a, b)` and `(b, a)` respectively, you cannot satisfy both with a single compound index; you need two. At the design stage, this is a question worth asking explicitly.

**Partial indexes do not change the rule.** A `partialFilterExpression` makes an index smaller (fewer documents indexed), but does not change how it sorts. The matched fields and directions still must align with the sort.

**The "ESR rule" is a guideline, not a law.** MongoDB documentation suggests indexing by Equality-Sort-Range (filter equality clauses, then sort fields, then range filters). This is a heuristic that often works, but the real rule is simpler: *the index must match the sort*. If your query filters on `a` (equality), sorts by `b`, and filters on `c` (range), a `{b: 1, a: 1, c: 1}` index is sub-optimal (the sort is not first) but if that is what you query by, that is what you need to index for — or accept that the sort is not indexed.

## Related concepts

See [`18_MONGODB_DENORMALIZATION_FOR_SORTING.md`](./18_MONGODB_DENORMALIZATION_FOR_SORTING.md) — why fields needed for sorting often come from other collections and must be copied into the document to be indexed.

See also [`12_MONGODB_PAGINATION_TOTAL_ORDER.md`](./12_MONGODB_PAGINATION_TOTAL_ORDER.md) — why sort keys must be unique (achieved with the `_id` tiebreaker) to make pagination deterministic.

## References

- [MongoDB Manual: Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/) — Field order and sort direction requirements
- [MongoDB Manual: Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/) — How to read query execution plans and detect when sorting happens in memory
- [MongoDB Manual: Index Intersection](https://www.mongodb.com/docs/manual/core/index-intersection/) — Why multiple indexes do not combine, reinforcing that you need the right single index
