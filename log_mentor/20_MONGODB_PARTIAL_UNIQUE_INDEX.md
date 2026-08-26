# MongoDB Partial Unique Index

> **Stack:** MongoDB · **Introduced in:** Syncing 218 sets where 30 have no abbreviation · **Date:** 2026-08-26

## Definition

A **partial unique index** is a unique constraint that applies only to documents matching a filter condition. In a standard unique index, MongoDB treats missing fields as null, and only one document can have a null value. A partial unique index eliminates this restriction for documents that do not match the filter — many documents can be without the indexed field or have it as null, as long as the documents that do have the field satisfy uniqueness.

## Why it exists

Consider a table of Pokémon TCG sets. Most have an official abbreviation (`MEG` for Mega Evolution, `SFA` for Scarlet & Violet 4.5), but 30 do not (special sets, unreleased sets, regional variants). If you create a unique index on `abbreviation` with no filter, a second set without an abbreviation cannot be inserted — because MongoDB stores the missing field as null, and only one document can have `abbreviation: null`.

The solution: create the unique index only over documents that actually have an abbreviation. Sets without abbreviations fall outside the index and can exist without triggering a uniqueness violation.

## How it works

**Standard unique index behavior:**
```python
# This allows only ONE document with abbreviation: null
db.sets.createIndex([("abbreviation", 1)], unique=True)
```

When the second document arrives without an abbreviation, the insert fails: `E11000 duplicate key error`.

**Partial unique index:**
```python
# This allows MANY documents without abbreviation
db.sets.createIndex(
    [("abbreviation", 1)],
    unique=True,
    partialFilterExpression={"abbreviation": {"$type": "string"}}
)
```

Now the index covers only documents where `abbreviation` is a string. Documents without the field, or with null, are not indexed and do not participate in the uniqueness constraint. The 30 sets without abbreviations coexist without conflict.

**Index options are immutable:** If the index already exists with different options (e.g., unique without `partialFilterExpression`), MongoDB will not rewrite it. Calling `createIndex` again with new options is a no-op. To change the options, drop the index and recreate it. This happens once, on first deployment after the change.

## In this project

**The problem:** The `sets` collection holds 218 documents, but only 188 have an official abbreviation (the code used in PTCG Live deck lists). A unique index on `abbreviation` was needed for import/export — to prevent two sets from claiming the same code — but 30 sets without codes could not coexist.

**The solution:**
```python
# backend/app/db/set_repository.py

async def ensure_indexes() -> None:
    # Unique but PARTIAL: only documents with a string abbreviation
    # can conflict. The other 30 sets without codes all have null and coexist.
    try:
        await _collection().create_index(
            [("abbreviation", ASCENDING)],
            unique=True,
            partialFilterExpression={"abbreviation": {"$type": "string"}},
        )
    except OperationFailure:
        # The index exists with the OLD options (unique=True, no partial filter).
        # MongoDB does not rewrite index options. Drop and recreate.
        await _collection().drop_index("abbreviation_1")
        await _collection().create_index(
            [("abbreviation", ASCENDING)],
            unique=True,
            partialFilterExpression={"abbreviation": {"$type": "string"}},
        )
```

The exception handler accounts for a migration scenario: if the index was created on a previous run with `unique=True` but no `partialFilterExpression`, it must be dropped and recreated with the new options. This runs once, on the first application startup after the code deploys.

The two query methods that use abbreviations now filter to only include sets with abbreviations:

```python
# Both methods now exclude sets without abbreviations
async def abbreviation_map() -> dict[str, str]:
    cursor = _collection().find(
        {"abbreviation": {"$type": "string"}},  # Only indexed documents
        {"abbreviation": 1}
    )
    return {doc["abbreviation"]: doc["_id"] async for doc in cursor}

async def id_map() -> dict[str, str]:
    cursor = _collection().find(
        {"abbreviation": {"$type": "string"}},  # Only indexed documents
        {"abbreviation": 1}
    )
    return {doc["_id"]: doc["abbreviation"] async for doc in cursor}
```

The logic is: sets without abbreviations are stored (they exist and have cards) but not returned by these maps. When a deck list references a code that does not resolve to a set, the import handler already knows what to do — report it unresolved and continue.

## Gotchas

**Index options are immutable.** Calling `createIndex` with new options on an existing index does nothing. You must drop the index first with `drop_index(index_name)`. The index name is the field name plus `_1` or `_-1` depending on sort direction — so `abbreviation_1` for an ascending index on `abbreviation`.

**`OperationFailure` is not a schema error, it is a deployment transition.** If you deploy code that tries to create an index with different options than what exists, the exception is caught at runtime, not at validation time. The catch-and-recreate pattern handles this gracefully, but only works if the operation is idempotent — dropping and recreating an index is safe to do multiple times.

**Partial indexes reduce index size but don't change the rule.** A partial unique index is smaller (fewer documents indexed), so it saves storage. But the uniqueness constraint within the filtered subset is the same: two documents with `abbreviation: "MEG"` still violate the constraint, and the error is the same.

**Filtering applies to both uniqueness and queries.** A query that tries to use the index must also pass documents that match the filter. Querying for all documents where `abbreviation` is not null is handled efficiently; querying where it is null or missing will not use the index (and will scan the collection).

## Related concepts

See [`19_MONGODB_COMPOUND_INDEX_MATCHING.md`](./19_MONGODB_COMPOUND_INDEX_MATCHING.md) — why index field order and sort direction must match queries exactly. Partial indexes do not change this rule.

See [`18_MONGODB_DENORMALIZATION_FOR_SORTING.md`](./18_MONGODB_DENORMALIZATION_FOR_SORTING.md) — denormalization allows querying on data from other collections, and partial indexes can make such a denormalized field unique across a subset of documents.

## References

- [MongoDB Manual: Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/) — How unique constraints work, and the behavior of null values
- [MongoDB Manual: Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/) — Creating and using indexes that cover only matching documents
- [MongoDB Manual: createIndexes Command](https://www.mongodb.com/docs/manual/reference/command/createIndexes/) — Full syntax including `partialFilterExpression`
