# Error Code with Parameters

> **Stack:** Python, JavaScript · **Introduced in:** feat/i18n-locale-switch · **Date:** 2026-08-29

## Definition

**Separating error from representation** means an error object carries a stable code (a wire constant the client recognizes) and the data needed to render it (`count`, `name`, etc.), but not the rendered message. The frontend looks up the message in its own catalogue.

## Why it exists

Rendering an error message in the backend and sending it as a string has two consequences:

1. **Duplication.** The backend carries English prose; the frontend needs Spanish. Suddenly the backend is bilingual, or the frontend guesses and translates, and the two diverge.

2. **Divergence is invisible.** The backend updates its Spanish text and ships it; the frontend's copy is unchanged. The user reads contradictory messages in the same error. No automated check catches this because both the wire protocol and the frontend are correct *independently* — they just disagree.

Two sources of truth for one sentence is the root of the problem. Removing the `message` field leaves one source: the client's catalogue. The backend's job is to say *why* it rejected a deck; the frontend's job is to say *how* that reason reads.

## How it works

**Backend:** An error object carries two fields:

- `code: str` — a stable identifier, never changes, never translated. Examples: `"wrong_size"`, `"too_many_copies"`. These are wire constants; the client hardcodes them into catalogue keys.
- `params: dict[str, str | int]` — the data the error message needs. For a "max 4 copies" rule broken, `params = {"name": "Iono", "count": 5, "max": 4}`. These are interpolated into the message by the client.

**Frontend:** For most codes the client looks up `` `violation.${code}` `` in its catalogue. `wrong_size` is the one exception: it needs two different sentences ("3 missing" vs "3 too many") that no plural rule distinguishes, so the client picks `violation.wrong_size_missing` or `violation.wrong_size_excess` by comparing the same numbers the backend sent, then passes `params` to the translation function and renders the result.

## In this project

**Backend model:**

```python
# backend/app/models/deck.py
class ViolationCode(str, Enum):
    """Reasons a deck is not legal.

    A stable wire value the client matches against its own catalogue key —
    never parsed, never shown, so it can stay in English while the sentence
    it selects is translated.
    """

    WRONG_SIZE = "wrong_size"
    TOO_MANY_COPIES = "too_many_copies"
    TOO_MANY_ACE_SPEC = "too_many_ace_spec"
    ILLEGAL_IN_FORMAT = "illegal_in_format"
    UNKNOWN_CARD = "unknown_card"


class Violation(BaseModel):
    code: ViolationCode
    # The words live in the client's catalogue; this carries only the numbers
    # and names they need. Keeping a rendered `message` here too would be two
    # sources of truth for one sentence, and the day the Spanish changes and
    # this does not, nobody notices.
    params: dict[str, str | int] = Field(default_factory=dict)
    # Cards involved, so the UI can point them out.
    card_ids: list[str] = Field(default_factory=list)
```

**Backend construction:** Five places in `deck_rules.py` build violations:

```python
# backend/app/services/deck_rules.py
if total != DECK_SIZE:
    # `count` is unsigned: the client picks "missing" or "too many" by
    # comparing `total` against `expected` itself, so it needs a magnitude,
    # not a sign it would have to strip back off. Named `count`, not `diff`,
    # so it's the same parameter the catalogue pluralises on.
    violations.append(Violation(
        code=ViolationCode.WRONG_SIZE,
        params={"expected": DECK_SIZE, "total": total, "count": abs(DECK_SIZE - total)},
    ))

for name, n in sorted(exceeded.items()):  # exceeded: name -> count, over MAX_COPIES_PER_NAME
    violations.append(Violation(
        code=ViolationCode.TOO_MANY_COPIES,
        params={"name": name, "count": n, "max": MAX_COPIES_PER_NAME},
        card_ids=ids_by_name[name],
    ))
```

**Frontend catalogue:**

```javascript
// frontend/src/i18n/en.js
violation: {
  wrong_size_missing: {
    one: 'A deck is {expected} cards: there are {total}, {count} missing',
    other: 'A deck is {expected} cards: there are {total}, {count} missing',
  },
  too_many_copies: '"{name}": {count} copies, the maximum is {max}',
}
```

```javascript
// frontend/src/i18n/es.js
violation: {
  wrong_size_missing: {
    one: 'Un mazo son {expected} cartas: hay {total}, falta {count}',
    other: 'Un mazo son {expected} cartas: hay {total}, faltan {count}',
  },
  too_many_copies: '«{name}»: {count} copias, el máximo son {max}',
}
```

**Frontend render:**

```javascript
// frontend/src/components/DeckValidation.jsx
import { useT } from '../i18n/index.jsx'

// One ViolationCode, two catalogue keys: "3 missing" and "3 too many" are
// different sentences, and no plural rule tells them apart — the choice has
// to be made here, by comparing the same numbers the backend sent.
function violationKey(v) {
  if (v.code === 'wrong_size') {
    return v.params.total < v.params.expected
      ? 'violation.wrong_size_missing'
      : 'violation.wrong_size_excess'
  }
  return `violation.${v.code}`
}

export default function DeckValidation({ validation, pendingTotal }) {
  const t = useT()
  const violations = validation.violations

  return (
    <ul className="violations">
      {violations.map((v, i) => (
        <li key={`${v.code}-${i}`}>{t(violationKey(v), v.params)}</li>
      ))}
    </ul>
  )
}
```

`card_ids` rides along on the wire (so a future UI can point out the offending
cards) but nothing renders it yet — the frontend only consumes `code` and
`params` today.

## Gotchas

**The raw API response is no longer self-explanatory.** In the Network tab, you see `{"code": "too_many_copies", "params": {"name": "Iono", "count": 5, "max": 4}}` with no message. This is traded for correctness: the machine is forced to be the source of truth, not a guess.

**A key missing from `es.js` alone does not render the raw key — it silently renders English.** `translate.js` checks the active locale first and falls back to `en` on a miss; if `en.js` has `violation.too_many_copies` but `es.js` does not, a Spanish user sees the *English* sentence, not the key, and no warning fires (the fallback found something, so `onMissing` is never called). The raw key only appears when a key is missing from *both* catalogues. This is exactly what `frontend/src/i18n/catalogues.test.js` exists to catch before merge, since nothing else would.

**Backwards-incompatibility is real.** A client built against an old backend that sends `{"message": "...", "code": "..."}` will not work with a new backend that sends only `{"code": "...", "params": {...}}`. Both must ship at the same time. This is not a gotcha of the pattern; it is a consequence of removing a field.

**Parameterization must be complete.** If a message says "Maximum 4 copies" but the params don't include `max: 4`, the frontend cannot render it correctly. The backend and catalogue must agree on which parameters each error carries. A comment in the code naming the params is not enough — a schema (TypeScript, Pydantic, `zod`, Protocol Buffers) enforces agreement automatically.

## Related concepts

This pattern answers the question "how does an error rendered on the backend stay correct as the user's language changes?" In isolation, it is overly complex — a single-language backend would not need codes and parameters. It is designed for i18n (entry 25): the catalogue holds every language, the backend is language-neutral, and the frontend matches them.

The **message catalogue** (entry 25) is where the text lives; **React Context** (entry 26) makes the locale available to all components that render errors.

## References

- [Pydantic Field defaults](https://docs.pydantic.dev/latest/api/fields/#pydantic.Field) — how to define a model field with a factory default
- [Enum in Python](https://docs.python.org/3/library/enum.html) — stable constants for error codes
- [Separation of Concerns](https://en.wikipedia.org/wiki/Separation_of_concerns) — the principle behind separating error from representation
