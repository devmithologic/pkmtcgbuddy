# Data Transfer Objects: Separate Input and Output Models

> **Stack:** PYDANTIC · **Introduced in:** first vertical slice — the `Match` resource · **Date:** 2026-08-08

## Definition

A **DTO** (Data Transfer Object) is a type that describes data crossing a boundary — an HTTP request,
a queue message — as opposed to the type used to store or operate on that data internally. In a REST
API it usually means a distinct model for what the client *sends* and what the server *returns*.

## Why it exists

The obvious design is one model per concept:

```python
class Match(BaseModel):
    id: str | None = None            # optional, "the server fills it"
    played_at: date
    result: MatchResult
    created_at: datetime | None = None
```

This has three problems, and they get worse over time.

**It accepts fields the client has no business setting.** `POST /api/matches` with
`{"id": "000000000000000000000000", "created_at": "1999-01-01T00:00:00Z"}` is now a valid request.
Whether it does damage depends on the handler remembering to ignore those fields — the security of
the endpoint rests on a line of code someone must not delete. This class of bug has a name: **mass
assignment**.

**It lies about what is guaranteed.** `id: str | None` says the id may be absent. On a response it
never is. Every consumer writes a null check for a case that cannot happen, and type checkers cannot
help.

**It couples the wire format to storage.** The day the database gains an internal column that must not
be public, there is no seam to hide it behind.

## How it works

Define one model per direction, and let inheritance carry the shared fields:

```python
class ItemCreate(BaseModel):     # what the client sends
    name: str

class ItemOut(ItemCreate):       # what the server returns
    id: str
    created_at: datetime
```

FastAPI wires them at both ends of the handler:

```python
@router.post("", response_model=ItemOut, status_code=201)
async def create_item(item: ItemCreate) -> ItemOut:
    ...
```

- The **parameter annotation** tells FastAPI to parse the JSON body and validate it against
  `ItemCreate`. Unknown fields are dropped, missing or wrong-typed fields produce an automatic `422`
  before the function body runs. Inside the handler, `item` is already valid.
- **`response_model`** filters the outgoing object to that shape. Anything not declared in `ItemOut`
  is stripped from the response even if the handler returns it — a safety net, not just documentation.

Both models also feed the OpenAPI schema, so `/docs` and any generated client stay accurate for free.

## In this project

```python
# backend/app/models/match.py
class MatchResult(str, Enum):
    WIN = "win"
    LOSS = "loss"
    TIE = "tie"


class MatchCreate(BaseModel):
    played_at: date
    opponent_archetype: str = Field(min_length=1, max_length=100)
    result: MatchResult
    notes: str | None = Field(default=None, max_length=1000)


class MatchOut(MatchCreate):
    id: str
    created_at: datetime
```

`MatchResult` is an `Enum` rather than a `str`, which means validation costs nothing to write:

```
POST {"result": "victoria"}
422 {"detail":[{"type":"enum","loc":["body","result"],
                "msg":"Input should be 'win', 'loss' or 'tie'"}]}
```

`loc` is the path to the offending field, so a client can highlight the exact input. Note the inherited
constraint too: `opponent_archetype` has `min_length=1`, so `""` is rejected — `required` in the HTML
form is a convenience, not a guarantee, because anyone can call the API without a browser. **Validation
belongs at the boundary the attacker cannot skip.**

## Gotchas

- **Inheriting the wrong way round.** `MatchOut(MatchCreate)` is right: output *extends* input. Writing
  `MatchCreate(MatchOut)` would make `id` required on creation.
- **`response_model` silently drops undeclared fields.** If a field is missing from the JSON response,
  check the output model before debugging the handler.
- **Enum members serialise as objects unless they subclass `str`.** `class MatchResult(str, Enum)` — drop
  the `str` and the value that reaches MongoDB is not JSON-friendly.
- **Constraints on the base class apply to both models.** Usually what you want; occasionally a reason to
  define a shared base instead of inheriting directly.
- **These models are not the database schema.** MongoDB enforces nothing. The document shape is decided
  by `match_to_document`, and validation is only ever as good as the code path that writes.

## Related concepts

Mass assignment; anti-corruption layer (the same idea applied to third-party APIs — the reason
`card_source.py` will exist in phase 3); OpenAPI schema generation;
`see 03_MONGODB_BSON_SERIALIZATION.md` for the translation between these models and stored documents.

## References

- [Extra Models — FastAPI](https://fastapi.tiangolo.com/tutorial/extra-models/) — official guidance on multiple models per resource, including input/output separation
- [Models — Pydantic](https://docs.pydantic.dev/latest/concepts/models/) — model definition, inheritance, and validation behaviour
- [Response Model — FastAPI](https://fastapi.tiangolo.com/tutorial/response-model/) — how `response_model` filters outgoing data
