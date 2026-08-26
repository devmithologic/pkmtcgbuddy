# Separate Sort and Search Fields

> **Stack:** Python · **Introduced in:** Hiding duplicate basic energy cards from search while keeping them in the database · **Date:** 2026-08-26

## Definition

A **search field** is a denormalized copy of data, precalculated and stored with the document, used only for filtering or searching — not for the user-facing value. Multiple search fields can exist on the same document to support different searching and sorting needs. This entry covers two patterns: (1) storing separate `sort_name` and `search_name` fields to filter and order differently, and (2) marking duplicate impressions to exclude them from search results while keeping the database record.

## Why it exists

**Two problems:**

1. **TCGdex names basic energies inconsistently.** `Metal Energy` (normal) and `Basic Metal Energy` (secret rare, golden). These are the same card, but the names are different enough that sorting alphabetically puts the secret first always. Solution: strip the prefix for sorting, but keep both versions for searching.

2. **Basic energies have 27+ reprints each, only one matters.** Metal Energy prints in Normal, Rare Holo, Secret Rare Ultra (shiny), and Hyper Rare (rainbow) in each set. Showing all 27 variants in the search interface is not helpful — the player building a deck wants the legal version (Normal, most recent). Solution: mark the duplicates as "don't offer in search" and filter them out, but keep them in the database for resolution (a saved deck might use the rare version).

Both solutions use precalculated fields that are computed at write time and used at query time.

## How it works

**Pattern 1: Separate fields for sorting vs. filtering**

Store two derived fields:
- `sort_name`: Used for `.sort()`. Strip prefixes, normalize to lowercase. Identical values group together.
- `search_name`: Used for `.find()` filter. Includes all variants of the name the user might search for.

```python
def sort_name(name: str, is_basic_energy: bool) -> str:
    """Name for ordering, with prefix stripped for basic energies."""
    bajo = name.lower()
    if is_basic_energy and bajo.startswith("basic "):
        return bajo.removeprefix("basic ")
    return bajo

def search_name(name: str, is_basic_energy: bool) -> str:
    """Name for searching, includes both forms."""
    if is_basic_energy:
        # Add "basic" to the search text so users can find it by either name
        return f"basic {sort_name(name, True)}"
    return name.lower()
```

The search for `q=metal` now finds both forms (because both normalizations contain "metal"), and they sort with the normal first (lower `sort_name` value) before the secret.

**Pattern 2: Marking and filtering duplicates**

For basic energies, calculate which printing should be offered to the user. Store a boolean `is_energy_duplicate` on each card, and filter it out in queries:

```python
# backend/app/db/card_repository.py

def energy_duplicates(documents: list[dict]) -> set[str]:
    """IDs of basic energy reprints that should NOT appear in search.
    
    Group by sort_name (the unified name for reprints), find the best reprint
    in each group using the same ranking as search, return all the others.
    """
    mejores: dict[str, dict] = {}
    basicas: list[dict] = []

    for doc in documents:
        if not doc.get("is_basic_energy"):
            continue
        basicas.append(doc)
        actual = mejores.get(doc["sort_name"])
        if actual is None or _es_mejor_impresion(doc, actual):
            mejores[doc["sort_name"]] = doc

    ganadores = {doc["_id"] for doc in mejores.values()}
    return {doc["_id"] for doc in basicas if doc["_id"] not in ganadores}

# Then, in _build_filter:
query: dict = {"is_energy_duplicate": {"$ne": True}}
```

The filter `{"$ne": True}` means: include documents where the field is missing (old documents, non-energies) or explicitly False. Exclude only documents marked True.

## In this project

**The measurement:** Of 322 basic energy impressions synced, 313 are marked as duplicates. The search offers 9 (one per type). The measurement was done by running the sync and observing the output:

```
energías básicas: 322 impresiones, 9 ofrecidas en el buscador
```

**The implementation:**

```python
# backend/app/db/card_repository.py

PLAIN_RARITY = "Common"

def sort_name(name: str, is_basic_energy: bool) -> str:
    bajo = name.lower()
    if is_basic_energy and bajo.startswith("basic "):
        return bajo.removeprefix("basic ")
    return bajo

def search_name(name: str, is_basic_energy: bool) -> str:
    if is_basic_energy:
        return f"basic {sort_name(name, True)}"
    return name.lower()

def printing_rank(is_basic_energy: bool, rarity: str | None) -> int:
    """0 for normal (offered), 1+ for special (duplicate)."""
    if is_basic_energy and rarity != PLAIN_RARITY:
        return 1
    return 0

def card_to_document(card: Card) -> dict:
    return {
        # ... other fields ...
        "sort_name": sort_name(card.name, card.is_basic_energy),
        "search_name": search_name(card.name, card.is_basic_energy),
        "printing_rank": printing_rank(card.is_basic_energy, card.rarity),
    }

# In the search flow:
async def search_cards(...):
    query = {"is_energy_duplicate": {"$ne": True}}
    if name:
        query["search_name"] = {"$regex": re.escape(name.lower())}
    
    cursor = (
        _collection()
        .find(query)
        .sort([
            ("sort_name", ASCENDING),
            ("printing_rank", ASCENDING),
            ("set_release_date", DESCENDING),
            ("_id", ASCENDING),
        ])
```

**In the sync flow:**

```python
# backend/app/services/card_sync.py

duplicadas = card_repository.energy_duplicates(documents)
for doc in documents:
    doc["is_energy_duplicate"] = doc["_id"] in duplicadas
```

The `energy_duplicates()` function receives all 15,000+ documents and examines only the basic energies. It groups them by `sort_name` (the unified name, with "Basic" prefix stripped), picks the best printing from each group (normal rarity, most recent), and marks the rest as `is_energy_duplicate = True`.

## Gotchas

**`search_name` and `sort_name` are never returned to the user.** These are implementation details. The user sees the original `name` field from the card model. The search works correctly because `.find()` filters by `search_name` and `.sort()` orders by `sort_name`, but if you ask the database for the document, it includes both fields and a confused developer might return `search_name` to the API by mistake.

**The "best" printing for basic energies is opinionated.** The function `printing_rank()` marks anything non-Common (Normal) as `rank=1`. The `_es_mejor_impresion()` tiebreaker then chooses the most recent. A Hyper Rare (rainbow) basic energy is newer and rarer, but the search hides it and shows the Common. This is intentional, but if the rule changes (e.g., "show Secret Rare versions"), the rank calculation must change and documents must be re-stamped.

**Filtering and ordering solve different problems.** The `is_energy_duplicate` field hides cards from search. The `printing_rank` field decides which one appears first. If you only applied the filter and did not use `printing_rank` in the sort, all 9 basic energies would appear, but in arbitrary order — one per type, but which Pikachu Illustrator art you get would depend on `_id`. The sort ensures deterministic order within each type.

**Old documents (written before this change) have no `is_energy_duplicate` field.** The filter `{"$ne": True}` treats a missing field as not-True, so old documents are included. This is safe — old documents predate the feature and the application behavior is backward-compatible. To clean them up, re-sync or run `card_sync --resort`.

## Related concepts

See [`18_MONGODB_DENORMALIZATION_FOR_SORTING.md`](./18_MONGODB_DENORMALIZATION_FOR_SORTING.md) — why sort keys are denormalized and stored at write time instead of computed at query time.

See [`19_MONGODB_COMPOUND_INDEX_MATCHING.md`](./19_MONGODB_COMPOUND_INDEX_MATCHING.md) — how the index on `sort_name` and `printing_rank` must exactly match the `.sort()` clause for the index to be used.

See [`23_MONGODB_DERIVE_ON_READ.md`](./23_MONGODB_DERIVE_ON_READ.md) — another use of `printing_rank` to select which reprint's image to use when the primary card has no image.

## References

- [MongoDB: Regex Searches](https://www.mongodb.com/docs/manual/reference/operator/query/regex/) — How `$regex` matches and why anchoring matters
- [MongoDB: Index Types and Performance](https://www.mongodb.com/docs/manual/core/indexes/) — When indexes help filtering vs. sorting
- [MDN: Regular Expression Denial of Service (ReDoS)](https://owasp.org/www-community/attacks/Regular_expression_Denial_of_Service_-_ReDoS) — Why escaping user input prevents regex attacks
