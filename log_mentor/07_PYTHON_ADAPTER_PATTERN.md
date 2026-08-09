# The Adapter Pattern (Anti-Corruption Layer)

> **Stack:** PYTHON · **Introduced in:** card search — talking to TCGdex · **Date:** 2026-08-08

## Definition

An **adapter** is a module that sits between your code and an external system, translating that
system's model into your own. When its purpose is specifically to stop a foreign model from leaking
into your domain, the pattern is also called an **anti-corruption layer** — a term from
Domain-Driven Design.

## Why it exists

Without one, the vendor's JSON shape spreads through the codebase by accident. A route handler reads
`payload["legal"]["standard"]`, a React component checks `card.rarity === "ACE SPEC Rare"`, a future
validator does the same. Nobody decided that TCGdex's field names would become the project's
vocabulary; it just happened, one convenient access at a time.

The bill arrives later, in one of three forms:

- **The provider changes.** A renamed field breaks call sites scattered across files, found one
  `KeyError` at a time in production.
- **The provider disappears.** This is not hypothetical here: `pokemontcg.io` was folded into a
  commercial product and its public endpoint degraded (see `CLAUDE.md`). Swapping providers means
  rewriting everything that touched the old shape.
- **The model does not fit.** TCGdex has no concept of "this card is an ACE SPEC" — only a rarity
  string. Every place that needs the concept re-derives it, and the magic string multiplies.

## How it works

Three parts, and the discipline is in keeping them separate:

1. **Your own model**, defined by what your application needs, not by what the API returns.
2. **A translation function**, the only code that reads the foreign shape.
3. **A public interface** in your vocabulary, so callers never see the vendor at all.

```python
# my_domain.py — what the application needs
class Thing(BaseModel):
    id: str
    is_special: bool          # a concept the vendor does not have

# vendor_adapter.py — the only file that knows the vendor
def _to_thing(payload: dict) -> Thing:
    return Thing(
        id=payload["identifier"],
        is_special=payload["tier"] == "SPECIAL_TIER",   # derived, not copied
    )

async def get_thing(thing_id: str) -> Thing | None: ...
```

The test for whether the boundary holds is mechanical: grep the codebase for the vendor's name. If it
appears outside the adapter, the boundary leaks.

## In this project

```python
# backend/app/services/card_source.py
BASE_URL = "https://api.tcgdex.net/v2/en"
ACE_SPEC_RARITY = "ACE SPEC Rare"

def _to_card(payload: dict) -> Card:
    legal = payload.get("legal") or {}
    rarity = payload.get("rarity")

    return Card(
        id=payload["id"],
        name=payload["name"],
        image_url=_image_url(payload.get("image")),
        category=CardCategory(payload["category"]),
        rarity=rarity,
        regulation_mark=payload.get("regulationMark"),
        legal_standard=bool(legal.get("standard", False)),
        legal_expanded=bool(legal.get("expanded", False)),
        is_ace_spec=rarity == ACE_SPEC_RARITY,     # derived
    )
```

Three translations worth noticing, because each is the adapter earning its place:

- **`is_ace_spec`** turns a vendor string into a domain boolean. `ACE_SPEC_RARITY` appears exactly
  once in the whole repository.
- **`_image_url`** hides that TCGdex returns image URLs without an extension: the caller wants a URL,
  not the knowledge that `/low.webp` must be appended.
- **`legal_standard` / `legal_expanded`** flatten a nested object, and `Card.is_legal_in(format)`
  turns them into a rule the deck validator will use without knowing where the data came from.

The adapter also owns failure translation, which belongs at the boundary for the same reason:

```python
# backend/app/routers/cards.py
except httpx.TimeoutException:
    raise HTTPException(status_code=504, detail="TCGdex tardó demasiado en responder.")
except httpx.HTTPError:
    raise HTTPException(status_code=502, detail="No se pudo consultar TCGdex.")
```

`502 Bad Gateway` and `504 Gateway Timeout` exist precisely for this: the server acting as a gateway
got a bad response, or none, from upstream. Returning `500` would claim the fault is ours and send
whoever debugs it to the wrong codebase.

## Gotchas

- **The adapter must not return the vendor's objects.** Returning a `dict` straight from the API is
  the leak in its most common disguise: the boundary looks present and enforces nothing.
- **A timeout is not optional.** `httpx` has no default timeout on a bare client. Without one, a slow
  upstream holds your connections until the pool is exhausted — the standard way a third party's
  outage becomes yours.
- **Resist mirroring the vendor's model "for completeness".** Fields nobody needs are fields that must
  be maintained. Our `Card` omits attacks, weaknesses, and abilities because no feature reads them yet.
- **One adapter per provider, not per endpoint.** Splitting by endpoint reintroduces the scatter the
  pattern exists to prevent.

## Related concepts

Ports and adapters (hexagonal architecture); dependency inversion; `see 02_PYDANTIC_DTO.md` — the same
instinct applied to the HTTP boundary instead of a third party; `see 08_HTTP_N_PLUS_ONE.md` for the
cost model that shaped this adapter's interface.

## References

- [Anti-Corruption Layer pattern — Microsoft Azure Architecture Center](https://learn.microsoft.com/en-us/azure/architecture/patterns/anti-corruption-layer) — the pattern, its context, and when it is not worth it
- [502 Bad Gateway — MDN](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/502) — the status code for an upstream failure
- [Timeouts — HTTPX](https://www.python-httpx.org/advanced/timeouts/) — why a default timeout matters and how to set one
