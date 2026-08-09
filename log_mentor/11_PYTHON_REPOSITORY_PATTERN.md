# The Repository Pattern

> **Stack:** PYTHON · **Introduced in:** moving card search from TCGdex to MongoDB · **Date:** 2026-08-09

## Definition

A **repository** is a module that encapsulates data access behind operations expressed in the
language of the domain — `search_cards(format=STANDARD)` — instead of the language of storage —
filters, cursors, indexes, connection handles.

## Why it exists

Without one, storage details leak into the code that calls it. A route handler builds a Mongo query
dict, a service knows a field is called `legal_standard`, a test needs a live database to run at all.
Each is a small convenience; together they weld the application to one database.

The cost shows up in three ways:

- **Swapping the store means touching every caller.** Query syntax is not portable.
- **Testing needs the real thing.** Logic that constructs `{"$regex": ...}` inline cannot be tested
  without a Mongo instance.
- **The same query gets rebuilt slightly differently in several places**, and one of them forgets a
  filter.

The pattern is not about anticipating a database migration — that rarely happens. It is about having
one place where "how we ask for cards" is decided.

## How it works

The repository exposes domain operations and hides everything else:

```python
# The caller says what it wants
result = await card_repository.search_cards(deck_format=DeckFormat.STANDARD, page=2)

# The repository decides how to get it
def _build_filter(...) -> dict:
    query = {}
    if deck_format:
        query[f"legal_{deck_format.value}"] = True
    return query
```

Two properties make it work, and both are easy to lose:

1. **It returns domain models, not database rows.** Returning a raw `dict` from Mongo leaks the
   schema through a function that looks like a boundary.
2. **Its interface names domain concepts.** `search_cards(ace_spec_only=True)` is domain language;
   `find({"is_ace_spec": True})` is storage language.

## In this project

The interesting part is the symmetry. `services/card_source.py` reads from TCGdex,
`db/card_repository.py` reads from MongoDB, and their public functions are deliberately identical:

```python
# services/card_source.py — remote
async def search_cards(name, deck_format, category, ace_spec_only, page, page_size) -> CardSearchResult
async def get_card(card_id) -> Card | None

# db/card_repository.py — local
async def search_cards(name, deck_format, category, ace_spec_only, page, page_size) -> CardSearchResult
async def get_card(card_id) -> Card | None
```

Same names, same parameters, same return types. That is what made switching the whole application
from live proxy to local storage a change of two imports in the router:

```python
# backend/app/routers/cards.py — before
from app.services import card_source
result = await card_source.search_cards(...)

# after
from app.db import card_repository
result = await card_repository.search_cards(...)
```

`card_source.py` did not change by a single line. It is still the only module that knows TCGdex
exists — but now the sync job calls it, not the user's request. That claim is checkable with
`git show 4536d90 --stat`.

The repository also owns storage decisions that no caller should see:

```python
# db/card_repository.py
"name_lower": card.name.lower(),   # precomputed for case-insensitive search
```

Storing a lowercase copy is a storage concern. Doing it at query time would mean transforming every
document on every search, which no index can help with.

## Gotchas

- **Leaking a `dict` defeats the whole thing.** The boundary must convert; `card_from_document` exists
  for exactly that.
- **A repository is not one class per table.** Group by domain concept, not by collection — the day a
  concept spans two collections, the per-table split fights you.
- **Beware the anaemic repository** that only wraps `find` and `insert`. If every caller still
  assembles filters, the repository is a rename, not a boundary.
- **`re.escape` is not optional** when user input becomes a regex. Without it, a user typing `(` gets
  an invalid-pattern error, and `(a+)+` is a denial-of-service vector through catastrophic
  backtracking (**ReDoS**).
- **Indexes belong here too.** `ensure_indexes()` lives in the repository because which fields are
  queried is the repository's knowledge, not the router's.

## Related concepts

`see 07_PYTHON_ADAPTER_PATTERN.md` — the same instinct pointed outward instead of downward; unit of
work; `see 12_MONGODB_PAGINATION_TOTAL_ORDER.md` for a bug that lives inside this module; dependency
inversion.

## References

- [Repository pattern — Microsoft .NET Architecture Guide](https://learn.microsoft.com/en-us/dotnet/architecture/microservices/microservice-ddd-cqrs-patterns/infrastructure-persistence-layer-design) — the pattern, its intent, and when it is overkill
- [Indexes — MongoDB Manual](https://www.mongodb.com/docs/manual/indexes/) — what an index does and when a query can use one
- [Regular expression Denial of Service — OWASP](https://owasp.org/www-community/attacks/Regular_expression_Denial_of_Service_-_ReDoS) — why user input must be escaped before it becomes a pattern
