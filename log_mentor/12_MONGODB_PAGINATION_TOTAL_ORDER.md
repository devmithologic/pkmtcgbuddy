# Pagination Needs a Total Order

> **Stack:** MONGODB · **Introduced in:** paginating the local card search · **Date:** 2026-08-09

## Definition

A **total order** is a sort key that never produces ties: for any two documents, one is definitively
before the other. Pagination requires one. Sorting by a field with duplicate values leaves the
database free to order the tied documents however it likes, and it may choose differently on each
query.

## Why it exists

Pagination looks like slicing one list. It is not. Each page is an **independent query**, executed at
a different moment, possibly with a different query plan. The only thing tying page 1 to page 2 is
the promise that both sort the same way.

Break that promise and documents move between requests:

```
Sorted by name only. Three cards share the name "Prime Catcher".

page 1 (skip 0,  limit 24)  → ... Prime Catcher(A), Prime Catcher(B)
page 2 (skip 24, limit 24)  → Prime Catcher(B), Prime Catcher(C) ...
                               ^ B appears twice; whichever card the first
                                 query put at index 24 has been displaced
```

A card can be shown twice, or skipped entirely, and nothing errors. The user just never sees it.

The failure is intermittent by nature: it needs a tie to land exactly on a page boundary. It will not
reproduce on a small dataset, and it will not reproduce reliably on a large one either.

## How it works

Append a field that is unique by construction — usually the primary key:

```python
.sort([("name_lower", ASCENDING), ("_id", ASCENDING)])
```

Now ties in `name_lower` are broken by `_id`, which is unique, so the order is total and identical
across queries.

Two details worth knowing:

**Why the database is allowed to reorder ties.** Sorting is not required to be *stable* — to preserve
the relative order of equal elements. MongoDB may satisfy a query with an index scan, an in-memory
sort, or a top-k sort depending on the limit, and each can order ties differently. The engine is not
misbehaving; the query simply did not specify enough.

**Index the tiebreaker too.** A compound index on `(name_lower, _id)` lets the sort be served by the
index. Without it, a large sort may need an in-memory pass — and MongoDB aborts sorts above 100 MB
unless allowed to spill to disk.

The deeper fix for large datasets is **keyset pagination** (also called seek pagination or cursor
pagination): instead of `skip(n)`, remember the last row's sort key and ask for rows after it. That
avoids a second problem this entry does not solve — `skip` gets slower the further you page, because
the database still walks the skipped documents.

## In this project

The bug appeared while verifying the sync against real data. Paginating gave the same 33 ACE SPEC
cards as a single query, no duplicates, no losses — but in a different order:

```
posición  paginado        una tirada
   13     sv05-154        sv08.5-117
   14     sv08.5-117      sv05-154
   21     sv05-157        sv08.5-119
   22     sv08.5-119      sv05-157
```

Two pairs swapped. Checking why:

```
> db.cards.aggregate([{$match:{is_ace_spec:true}},
                      {$group:{_id:"$name_lower", n:{$sum:1}}},
                      {$match:{n:{$gt:1}}}])

nombres ACE SPEC repetidos: 4
  prime catcher x2 · scoop up cyclone x2 · sparkling crystal x2 · maximum belt x2
```

Card names are not unique — the same card is reprinted across sets, and there are dozens of cards
named "Pikachu". The sort key admitted ties, so the engine resolved them differently for
`limit(25)` than for `limit(101)`.

Here the reordering stayed inside a page, so nothing was lost. That is luck, not correctness: with a
tie straddling the boundary, a card disappears.

```python
# backend/app/db/card_repository.py
.sort([("name_lower", ASCENDING), ("_id", ASCENDING)])

# ensure_indexes()
await collection.create_index([("name_lower", ASCENDING), ("_id", ASCENDING)])
```

Verified after the fix: three consecutive pages of Standard produce exactly the same sequence as one
query of 72, with zero duplicates, repeated three times.

## Gotchas

- **A single query hides the bug completely.** It only appears across paginated requests, which is
  why it survives manual testing.
- **`skip` degrades with depth.** `skip(10000)` makes the database walk 10,000 documents. Keyset
  pagination is the fix when pages go deep.
- **Data changing between pages shifts everything.** If a card is inserted while the user reads page
  1, page 2 shifts by one. A total order does not solve this; keyset pagination does.
- **The same rule applies to SQL.** `ORDER BY name LIMIT 24 OFFSET 24` has exactly this bug.
- **`_id` is a good tiebreaker only because it is unique.** Any unique field works; a "created_at"
  timestamp usually does not.

## Related concepts

`see 11_PYTHON_REPOSITORY_PATTERN.md` — the module this lives in; `see 08_HTTP_N_PLUS_ONE.md` —
another bug that only appears at scale; keyset/cursor pagination; sort stability.

## References

- [cursor.sort() — MongoDB Manual](https://www.mongodb.com/docs/manual/reference/method/cursor.sort/#sort-consistency) — the explicit statement that sorts on non-unique keys are not consistent across executions
- [Compound indexes — MongoDB Manual](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/) — why field order in a compound index matters for sorting
