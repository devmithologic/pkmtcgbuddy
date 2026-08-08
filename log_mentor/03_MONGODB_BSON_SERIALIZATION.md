# BSON Types and the Python Translation Layer

> **Stack:** MONGODB · **Introduced in:** first vertical slice — storing and reading `Match` documents · **Date:** 2026-08-08

## Definition

**BSON** ("Binary JSON") is the binary format MongoDB uses to store documents. It extends JSON with
types JSON lacks — `ObjectId`, `Date`, `Decimal128`, binary data — and omits some Python types
entirely. Moving data between Python and MongoDB therefore requires translation in both directions.

## Why it exists

JSON has six types. That is too few for a database: no distinction between integers and floats, no
binary blobs, no native dates. BSON adds them, and adds length prefixes so a driver can skip fields
without parsing them.

The cost is a type system that matches neither JSON nor Python. Two mismatches show up immediately in
any Python + MongoDB + HTTP application:

**`ObjectId` is not JSON-serialisable.** Every document has an `_id`, and by default it is a
12-byte `ObjectId`. Returning a document straight from a query gives:

```
TypeError: Object of type ObjectId is not JSON serializable
```

which surfaces as a `500` *after* the handler returned successfully, because serialisation happens
during response rendering. The traceback points at the framework, not at your code.

**BSON has no date-without-time type.** Python distinguishes `datetime.date` from
`datetime.datetime`; BSON only has `Date`, a millisecond timestamp. Inserting a `date`:

```
InvalidDocument: cannot encode object: datetime.date(2026, 8, 8), of type: <class 'datetime.date'>
```

## How it works

`ObjectId` is not a random identifier. It is 12 bytes with structure:

```
4 bytes  Unix timestamp (seconds)
5 bytes  random per-process value
3 bytes  incrementing counter
```

The leading timestamp means `ObjectId`s are roughly ordered by creation time — sorting by `_id`
approximates sorting by age, and `_id` carries a creation date without a separate field. "Roughly",
because the resolution is one second and clocks across machines differ.

The general pattern is a pair of translation functions at the storage boundary:

```python
def to_document(model):    # Python -> BSON-safe dict
    ...

def from_document(doc):    # BSON dict -> API model
    ...
```

Keeping them adjacent matters: every asymmetry between them is a bug, and they are much easier to
check side by side than scattered across handlers.

## In this project

```python
# backend/app/models/match.py
def match_to_document(match: MatchCreate) -> dict:
    return {
        "played_at": datetime.combine(match.played_at, time.min, tzinfo=timezone.utc),
        "opponent_archetype": match.opponent_archetype,
        "result": match.result.value,
        "notes": match.notes,
        "created_at": datetime.now(timezone.utc),
    }


def match_from_document(document: dict) -> MatchOut:
    return MatchOut(
        id=str(document["_id"]),
        played_at=document["played_at"].date(),
        ...
    )
```

Three conversions, each forced by BSON:

| Field | Python | Stored as | Why |
| --- | --- | --- | --- |
| `played_at` | `date` | `datetime` at 00:00 UTC | BSON has no date-only type |
| `result` | `MatchResult` enum | `str` | enum members are not BSON-encodable |
| `_id` | — | `ObjectId` | converted to `str` on the way out |

The midnight component is padding with no meaning. `match_from_document` calls `.date()` to discard
it, so the API never reports a precision the user did not supply. Storing it and reading it back
unchanged would be worse than the original problem: the data would look precise and be wrong.

What this actually looks like on disk:

```
> db.matches.findOne()
{
  _id: ObjectId('6a76e61f2a74dbe2a147ea5e'),
  played_at: ISODate('2026-08-08T00:00:00.000Z'),
  result: 'win',
  created_at: ISODate('2026-08-08T08:17:35.527Z')
}
```

Inspecting documents with `mongosh` is the fastest way to confirm what was really written, as opposed
to what the API claims it wrote.

## Gotchas

- **The `TypeError` appears far from its cause.** The handler succeeds; serialisation fails afterwards.
  If a `500` has no traceback in your own code, suspect a non-serialisable return value.
- **Naive datetimes are stored as UTC anyway.** PyMongo assumes UTC for `datetime` objects without
  `tzinfo`, so a local-time value is silently shifted. Always construct with `timezone.utc`.
- **Reads always return `datetime`, never `date`.** Round-tripping is not symmetric; `.date()` on the way
  out is mandatory, not cosmetic.
- **`ObjectId` timestamps are not a substitute for `created_at`.** One-second resolution, and it reflects
  when the id was generated, not when the row was meant to exist.
- **A global JSON encoder is the tempting shortcut.** It works and hides the problem; the price is that
  the next developer cannot see where the boundary is.

## Related concepts

`see 02_PYDANTIC_DTO.md` for the models these functions convert between; document modelling
(embed vs. reference), which is phase 2; `Decimal128` and why floats are wrong for money.

## References

- [BSON Types — MongoDB Manual](https://www.mongodb.com/docs/manual/reference/bson-types/) — the complete type list and their JSON equivalents
- [ObjectId — PyMongo API](https://pymongo.readthedocs.io/en/stable/api/bson/objectid.html) — structure, generation, and the embedded timestamp
- [Dates and Times — PyMongo](https://pymongo.readthedocs.io/en/stable/examples/datetimes.html) — timezone handling and the naive-datetime trap
