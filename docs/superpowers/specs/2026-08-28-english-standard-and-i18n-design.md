<!-- Design spec. Written before implementation, kept afterwards as the record of what was
decided and why. The durable decisions from this document graduate into docs/decisions.md;
this file keeps the reasoning that is too long for a table row. -->

# English as the source language, and a Spanish translation layer

**Date:** 2026-08-28 · **Status:** approved, not yet implemented

## Goal

Two things, in this order:

1. Make **English the development standard** of the repository — identifiers, comments,
   docstrings and user-visible strings.
2. Add a **language selector** so the interface can be read in English or Spanish.

The second is the feature the user asked for. The first is what makes the second coherent:
translating a Spanish-source app into English leaves the codebase bilingual forever, and the
codebase is already macaronic today (`openSession(id, editar = false)`, `dentro`, `camino`,
`MUESTRA_MINIMA` sitting next to `openDeckId`, `deckFolderId`, `played_at`).

This repository exists so its author can add full-stack engineering to their career. An English
codebase is the industry norm and the one a reader outside Spain can review.

## Decisions

Each row was an explicit choice, not a default.

| Question | Decision | Why |
| --- | --- | --- |
| How far does "English standard" go? | Everything: identifiers, comments, docstrings, docs | A half-translated repo is worse than either language pure |
| Default locale on first visit | Detect from `navigator.language`, then remember | What users expect; an explicit choice always beats detection afterwards |
| Where is the choice stored | `localStorage` | Survives reload; no backend involvement |
| Do backend messages get translated? | Deck-legality violations yes; HTTP `detail` no | Violations are shown in the UI on every deck screen; 404 details are impossible-state errors |
| Key style | Namespaced dotted keys, two full catalogues | Context per key, missing translations detectable, a third language costs nothing |
| Library | None — hand-rolled | `CLAUDE.md`: understand the manual version before adopting the shortcut |

### Why not `react-i18next`

It is what a production team would reach for, and it would supply ICU plurals, `<Trans>` for
rich text, lazy catalogue loading and extraction tooling. It is rejected **for now** because
this repository's stated purpose is understanding mechanisms, and ~40 kB of dependency would
hide exactly the mechanism this task teaches. Adopting it later, deliberately, knowing what it
replaces, is the intended end state — not a reversal of this decision.

### Why not source-string-as-key

`t('Save deck')` with a single Spanish catalogue and English as the natural fallback was the
serious alternative (it is the gettext and Lingui model). Rejected on two failure modes that
bite at ~200 strings: `'Name'` as a field label and as a column header share one key and cannot
take different Spanish; and fixing a typo in the English source silently breaks the Spanish
lookup with no error.

## Non-goals

Explicitly out of scope, so that "we forgot" is distinguishable from "we decided":

- **Card, set and format names.** The catalogue is synced from TCGdex in English
  (`BASE_URL = "https://api.tcgdex.net/v2/en"`). Translating them means a second sync and
  double storage, and the competitive community names cards in English anyway.
- **HTTP `detail` strings** from the routers. They describe impossible states
  (`No such deck {id}`), not text a user is meant to act on. They become English with the rest
  of the code and stay untranslated.
- **Date localisation.** Dates render raw today (`2026-08-28`). Localising them is a task with
  real substance — `new Date('2026-08-28')` parses as UTC and renders as the 27th in a negative
  offset, so the date must be built from components — and it belongs to a separate
  quality-of-life change.
- **A third language.** The design must not make one expensive, but nothing is built for it.
- **A test suite.** Its absence shapes the verification plan below, but writing it is phase 5
  of the project and not this work.

---

## Phase 0 — record the convention

Before any code moves, the convention that governs it changes:

- `CLAUDE.md` — the line "Code and comments are written in Spanish; `CLAUDE.md` and
  `log_mentor/` in English" is replaced by an English-everywhere rule.
- `docs/decisions.md` — new rows, and the corresponding index rows in the `CLAUDE.md` table:
  - English is the source language of code and UI
  - The UI language is chosen in the client, detected then remembered
  - A `Violation` carries a code and parameters, never prose

## Phase 1 — anglicisation

Behaviour-preserving by construction. ~50 files, roughly 2 000–2 500 lines of prose.
`docs/` (536 lines) and `log_mentor/` (2 969 lines) are already English and are not touched.

The work is split by **risk**, not by directory, because the risk differs by an order of
magnitude and the repository has no tests to catch a mistake.

### 1a — inert changes: comments and docstrings

Cannot change behaviour, and this is provable rather than merely believed.

**Verification:** a throwaway script parses every `.py` before and after with `ast.parse`,
strips all docstring nodes from both trees, and compares `ast.dump`. Identical dumps prove no
statement changed. Standard library only; nothing to install. The same technique is worth
knowing for any large mechanical refactor.

The frontend has no equivalent stdlib parser. `npm run lint` and `npm run build` must pass, and
the diff is reviewed with the knowledge that a comment-only hunk cannot execute.

### 1b — identifiers

Small and reviewable, but genuinely able to break things: a rename must be complete.

- Backend: `_limpia_nombre`, `crearia_ciclo`, and local variables (`carpeta`, `carpetas`,
  `carta`, `cartas`, `clave`, `detalle`, `fecha`, `fecha_a`, `fecha_c`, `filtro`, …).
- Frontend: `camino`, `carpeta`, `dentro`, `mazosAqui`, `MUESTRA_MINIMA`, `nombreEditable`, and
  the parameters `editar` and `nuevo`.
- CSS class names are already English and are not touched.

Separate commits from 1a, grouped per file or per coherent group, so that a revert is cheap.

**Not renamed:** anything that crosses the wire. API field names (`played_at`,
`deck_version_id`) are already English and are contract, not style.

### 1c — user-visible strings

~200 strings across 14 components move to English. This changes what is on screen but not what
the code does.

Two hand-rolled plurals must be fixed rather than translated, because they are untranslatable
as written — they split a word and glue a suffix, which does not survive contact with a
language whose plural is not a suffix in the same place:

- `DeckList.jsx:303` — `` `${dentro} ${dentro === 1 ? 'mazo' : 'mazos'}` ``
- `DeckStats.jsx:160` — `sesion` followed by `{n === 1 ? '' : 'es'}`

They become whole strings, and in phase 2 whole plural entries.

**At the end of phase 1 the application is English-only.** Spanish returns in phase 2. This is
the order, not a regression.

---

## Phase 2 — the i18n subsystem

### Module layout

```
frontend/src/i18n/
  index.jsx   LocaleProvider, useT(), useLocale()
  en.js       source catalogue
  es.js       translation
```

### Why React Context

A module-level variable would change the language but React would never know to re-render:
nothing connects the mutation to the render. Context is the mechanism that turns "a value
changed" into "the components reading it repaint".

One context carrying `{ locale, setLocale, t }` is correct here. Splitting it to narrow
re-renders would be optimising against the thing we actually want — on a language change,
every consumer *should* repaint.

### `t(key, params)` — the resolution chain

1. Walk the dotted key into the current locale's catalogue.
2. Miss → walk it into `en`. This is the **fallback locale**.
3. Miss again → return the key itself and `console.warn` in development. A missing translation
   must be something the developer finds, not something a user reports.
4. If the resolved value is an object and `params.count` is present, select the plural form
   with `new Intl.PluralRules(locale).select(params.count)` — a browser-native API that knows
   Polish has three categories and Arabic six. `count` is a reserved parameter name: it is the
   only one that drives plural selection.
5. Interpolate `{name}` placeholders from `params`.

### Catalogue shape

Keys mirror the component tree, so a key names the *place* in the UI and two "Save" buttons on
different screens can take different Spanish.

```js
// en.js
export default {
  nav: { sessions: 'Sessions', decks: 'Decks', cards: 'Cards' },
  deckList: {
    empty: 'No decks yet.',
    inside: { one: '{count} deck', other: '{count} decks' },
  },
  violation: {
    too_many_copies: '"{name}": {n} copies, the maximum is {max}',
  },
}
```

Namespaces are camelCase, mirroring component names. The one exception is `violation.*`, whose
leaves are snake_case because they are not invented here: they are the wire values of
`ViolationCode`, and deriving the key from the code is what removes the mapping table that
would otherwise drift.

### Locale state

- **Initial:** `localStorage.getItem('locale')`, else `navigator.language.startsWith('es') ? 'es' : 'en'`.
- **On change:** state, `localStorage.setItem`, and `document.documentElement.lang = locale`.

Setting `lang` on `<html>` is not decoration. A screen reader picks its voice from it, and
Spanish read with English phonetics is unintelligible.

### The selector

A two-button `EN | ES` segmented control in the `<header>`, following the existing
`.view-switch` and `.deck-modes` pattern.

Deliberately **not** the `Menu` component, despite the standing decision that every popover is
a `Menu`: a popover for two options is more machinery than the job needs. If a third language
arrives, that decision reverses.

### The `Violation` contract

`Violation` gains `params: dict[str, str | int] = Field(default_factory=dict)` and **loses
`message`**. The frontend renders `t('violation.' + v.code, v.params)`.

Dropping `message` rather than keeping it as an English fallback follows this repository's own
rule: two sources of truth diverge. Keeping it guarantees that one day the Spanish text changes
and the `message` does not, and nobody notices. The cost is that the raw API response is no
longer self-explanatory in the network tab — accepted, in exchange for it being unable to lie.

Touched: `backend/app/models/deck.py` (the model), `backend/app/services/deck_rules.py` (five
construction sites), `frontend/src/components/DeckValidation.jsx` (the render), `docs/api.md`.

The seam already existed. `ViolationCode`'s own docstring says it is there "so the frontend can
decide how to present it without parsing Spanish text" — this phase spends what was saved.

### Strings that must not be translated

The traps, listed because they are the ones that get translated by reflex:

- **`SESSION_TYPES[].value`** (`league`, `cup`, `challenge`, `online`, `testing`) — these match
  the `SessionType` enum in the backend. The `label` is translated; the `value` never is.
- **`SessionList.jsx:20`, `toLocaleDateString('en-CA')`** — not display formatting. It is the
  trick that yields `YYYY-MM-DD`, which is what `<input type="date">` requires. "Localising" it
  breaks the form.
- **Card, set and format names** — English data from the catalogue.
- **PTCG Live import/export text** — an interoperability format, not prose.
- **HTTP `detail` strings** — English, by decision.

---

## Verification

There is no test suite, so verification is explicit and manual where it must be.

| Phase | Check |
| --- | --- |
| 1a | AST-equality script over `backend/app/**/*.py`; `npm run lint` and `npm run build` |
| 1b | Lint and build; grep that no old identifier survives; start the API and hit one endpoint per router |
| 1c | Walk every screen: sessions list and detail, decks list, deck builder, deck stats, card search |
| 2 | Both locales on every screen; reload persists the choice; a fresh profile detects correctly; `<html lang>` updates; an intentionally missing key warns and falls back |

## Work split

Per `CLAUDE.md` — the developer writes the code that carries a new concept; Claude writes the
boilerplate.

- **Claude:** all of phase 1. The two catalogues. Threading `t()` through the 14 components.
  The backend `Violation` change.
- **The developer:** `i18n/index.jsx` — the provider, the hook and `t`. That file is where
  Context, the fallback chain, interpolation and `Intl.PluralRules` live, and it is the whole
  lesson. Claude supplies the shape and reviews.
