# Locale Switch (i18n) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the interface be read in English or Spanish, chosen by a switch in the header, detected from the browser on the first visit and remembered afterwards.

**Architecture:** A hand-rolled message catalogue. The pure translation function lives in `i18n/translate.js` with no React in it at all — which is what makes it unit-testable under `node --test` with zero new dependencies — and `i18n/index.jsx` binds it to React through a Context. The backend stops sending prose for deck-legality violations and sends a code plus parameters instead, so the client owns every word on the screen.

**Tech Stack:** React 19 Context, `Intl.PluralRules`, `localStorage`, `node:test` + `node:assert` (both built into Node 24). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-28-english-standard-and-i18n-design.md`

**Prerequisite:** `docs/superpowers/plans/2026-08-28-english-standard.md` must be complete. This plan lifts the English UI copy that plan produced straight into the source catalogue.

## Deviation from the spec

The spec puts `t()` inside `i18n/index.jsx`. This plan splits it into `i18n/translate.js` (pure, no React, no JSX) with `index.jsx` keeping only the Context binding.

The reason is testability, and it is not cosmetic: `node --test` runs plain `.js` but not JSX, so a `t()` living beside a Provider is a `t()` that cannot be unit-tested without adding a build step and a test framework. `t()` is the one piece of genuinely tricky pure logic in this change — a fallback chain, plural selection and interpolation, each with edge cases — and it is exactly where a bug would hide. Separating the pure core from the framework binding is the standard move, and it earns a test suite for free.

## Global Constraints

- **No new dependencies.** Not `react-i18next`, not `vitest`. The spec rejects a library explicitly and gives the reason.
- **`count` is a reserved parameter name.** It is the only parameter that drives plural selection. Do not use it for anything else.
- **`en` is the fallback locale.** Every key must exist in `en.js`; `es.js` may lag, and a gap must degrade to English rather than to a raw key.
- **Never translate:** `SESSION_TYPES[].value`, `ViolationCode` wire values, card/set names, the PTCG Live import/export format, or `toLocaleDateString('en-CA')` in `SessionList.jsx` (it produces `YYYY-MM-DD` for `<input type="date">`).
- **Dates stay as they are.** Localising `played_at` is a non-goal of this spec — `new Date('2026-08-28')` parses as UTC and renders as the 27th in a negative offset, which makes it a task with its own substance.
- Every task ends with a commit.

## Catalogue key conventions

- Namespaces are camelCase and mirror component names: `deckList`, `deckBuilder`, `sessionDetail`, `cardSearch`.
- Shared copy that genuinely is one string in one voice goes under `common` (`common.save`, `common.cancel`, `common.delete`). Two buttons that merely happen to read the same today do **not** share a key — that is the whole reason this style was chosen over source-string keys.
- `violation.*` leaves are snake_case, because they are not invented here: they are `ViolationCode` wire values, and deriving the key from the code is what removes a mapping table that would otherwise drift.
- A plural entry is an object `{ one, other }`. Both branches are whole sentences — never a stem plus a suffix.

---

## Task 1: The pure translation core

**Files:**
- Create: `frontend/src/i18n/translate.js`
- Test: `frontend/src/i18n/translate.test.js`
- Modify: `frontend/package.json` — add a `test` script

**Interfaces:**
- Consumes: nothing
- Produces:
  ```js
  createTranslator(catalogues, locale, { onMissing }) -> t
  t(key: string, params?: object) -> string
  ```
  `catalogues` is `{ en: {...}, es: {...} }`. `onMissing(key, locale)` is called when a key resolves in no catalogue, and defaults to a `console.warn`. Task 3 calls `createTranslator`; Tasks 5–8 and 10 call `t`.

**Written by the developer.** This file is the lesson — the fallback chain, interpolation and `Intl.PluralRules` all live here. Claude supplies the tests and reviews.

- [ ] **Step 1: Add the test script**

```json
"scripts": {
  "dev": "vite",
  "build": "vite build",
  "lint": "oxlint",
  "test": "node --test src/i18n/",
  "preview": "vite preview"
}
```

No dependency is added. Node 24 ships `node:test` and `node:assert`. Vite never bundles `translate.test.js` because nothing imports it.

- [ ] **Step 2: Write the failing tests**

```js
// frontend/src/i18n/translate.test.js
import assert from 'node:assert/strict'
import { test } from 'node:test'

import { createTranslator } from './translate.js'

const catalogues = {
  en: {
    common: { save: 'Save' },
    deckList: {
      empty: 'No decks yet.',
      inside: { one: '{count} deck', other: '{count} decks' },
    },
    violation: { too_many_copies: '"{name}": {count} copies, the maximum is {max}' },
  },
  es: {
    common: { save: 'Guardar' },
    deckList: {
      inside: { one: '{count} mazo', other: '{count} mazos' },
    },
  },
}

function translator(locale, onMissing = () => {}) {
  return createTranslator(catalogues, locale, { onMissing })
}

test('resolves a dotted key in the active locale', () => {
  assert.equal(translator('es')('common.save'), 'Guardar')
})

test('interpolates named parameters', () => {
  const t = translator('en')
  assert.equal(
    t('violation.too_many_copies', { name: 'Iono', count: 5, max: 4 }),
    '"Iono": 5 copies, the maximum is 4',
  )
})

test('leaves a placeholder alone when no parameter is supplied', () => {
  // Better a visible {max} than a silent "undefined" on screen.
  const t = translator('en')
  assert.equal(
    t('violation.too_many_copies', { name: 'Iono', count: 5 }),
    '"Iono": 5 copies, the maximum is {max}',
  )
})

test('falls back to English when the key is missing from the active locale', () => {
  // deckList.empty exists only in `en`.
  assert.equal(translator('es')('deckList.empty'), 'No decks yet.')
})

test('returns the key and reports it when it exists in no catalogue', () => {
  const missing = []
  const t = translator('es', (key, locale) => missing.push([key, locale]))
  assert.equal(t('deckList.nothingHere'), 'deckList.nothingHere')
  assert.deepEqual(missing, [['deckList.nothingHere', 'es']])
})

test('does not crash on a key that walks through a string', () => {
  // 'common.save.deeper' asks for a property of a string.
  const t = translator('en', () => {})
  assert.equal(t('common.save.deeper'), 'common.save.deeper')
})

test('selects the singular plural form', () => {
  assert.equal(translator('en')('deckList.inside', { count: 1 }), '1 deck')
  assert.equal(translator('es')('deckList.inside', { count: 1 }), '1 mazo')
})

test('selects the plural form', () => {
  assert.equal(translator('en')('deckList.inside', { count: 7 }), '7 decks')
  assert.equal(translator('es')('deckList.inside', { count: 7 }), '7 mazos')
})

test('treats zero as plural in both locales', () => {
  // Not a given: some languages have a `zero` category. English and Spanish do not.
  assert.equal(translator('en')('deckList.inside', { count: 0 }), '0 decks')
  assert.equal(translator('es')('deckList.inside', { count: 0 }), '0 mazos')
})

test('reports a plural entry used without a count instead of rendering an object', () => {
  // Returning the object would make React throw "Objects are not valid as a React child".
  const missing = []
  const t = translator('en', (key) => missing.push(key))
  assert.equal(t('deckList.inside'), 'deckList.inside')
  assert.deepEqual(missing, ['deckList.inside'])
})
```

- [ ] **Step 3: Run the tests and watch them fail**

Run: `cd frontend && npm test`
Expected: every test fails with `Cannot find module './translate.js'`.

- [ ] **Step 4: Write `translate.js`**

The shape, for the developer to fill in:

```js
/**
 * The translation core, deliberately free of React.
 *
 * Keeping it framework-free is what lets `node --test` run it directly: the
 * moment a Provider lives in the same file, the file is JSX and the test needs
 * a build step and a test framework to exist.
 */

const FALLBACK_LOCALE = 'en'

// Walks a dotted key. Returns undefined rather than throwing when the path runs
// through a string or off the end of the object — a missing key is an ordinary
// event here, not an exception.
function lookup(catalogue, key) { /* … */ }

// Replaces {name} from params. An absent parameter is left visible on purpose:
// "{max}" on screen is a bug you notice, "undefined" is a bug you ship.
function interpolate(template, params) { /* … */ }

export function createTranslator(catalogues, locale, { onMissing } = {}) {
  const report = onMissing ?? ((key, loc) => console.warn(`[i18n] missing "${key}" (${loc})`))

  return function t(key, params = {}) {
    // 1. active locale  2. fallback locale  3. report and return the key
    // 4. plural entry -> Intl.PluralRules  5. interpolate
  }
}
```

Four things worth getting right:

1. `lookup` must survive `common.save.deeper`, where the path runs into a string. `reduce` with a guard, not optional chaining alone.
2. `new Intl.PluralRules(locale).select(count)` returns a category name — `'one'`, `'other'`, and in other languages `'few'`, `'many'`, `'zero'`, `'two'`. Fall back to `entry.other` when the category has no entry, so adding a language later degrades instead of crashing.
3. A plural entry reached without `params.count` must **not** be returned as-is. React throws `Objects are not valid as a React child` and the whole screen goes blank. Report it and return the key.
4. Construct `Intl.PluralRules` lazily or memoise it. It is not free, and `t` is called on every render of every component.

- [ ] **Step 5: Run the tests and watch them pass**

Run: `cd frontend && npm test`
Expected: 10 passing, 0 failing.

- [ ] **Step 6: Lint**

Run: `cd frontend && npm run lint`
Expected: passes.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/i18n/translate.js frontend/src/i18n/translate.test.js frontend/package.json
git commit -m "feat: add the pure translation core with a fallback chain and plurals"
```

---

## Task 2: Extract the catalogues

**Files:**
- Create: `frontend/src/i18n/en.js`
- Create: `frontend/src/i18n/es.js`

**Interfaces:**
- Consumes: the key conventions above
- Produces: two default-exported nested objects with identical key sets. Tasks 5–8 and 10 read keys from them; every key those tasks use must exist here first.

**Written by Claude.** This is transcription, not design.

- [ ] **Step 1: Inventory every string in the interface**

```bash
cd frontend/src
grep -rnoE ">[^<>{}]+<|(placeholder|title|aria-label|alt)=\"[^\"]+\"" App.jsx components/ | grep -vE ">\s*<"
grep -rnoE "'[A-Z][^']{2,}'" App.jsx components/ sessionTypes.js
```

Read both lists in full. Each entry is either a catalogue key or an explicit exclusion under the Global Constraints. Write the exclusions down as you skip them; a silent skip is indistinguishable from a miss.

- [ ] **Step 2: Write `en.js` from the strings already on screen**

The English copy produced by the previous plan is the source of truth. Copy it verbatim — rewording here means rewording the Spanish too, for nothing.

```js
export default {
  nav: { sessions: 'Sessions', decks: 'Decks', cards: 'Cards' },

  common: {
    save: 'Save',
    cancel: 'Cancel',
    delete: 'Delete',
    back: 'Back',
    // …
  },

  sessionType: {
    league: 'League',
    cup: 'Cup',
    challenge: 'Challenge',
    online: 'Online',
    testing: 'Testing',
  },

  deckList: {
    empty: 'No decks yet.',
    emptyFolder: 'This folder is empty.',
    allDecks: 'All decks ({count})',
    inside: { one: '{count} deck', other: '{count} decks' },
    // …
  },

  violation: {
    unknown_card: {
      one: '{count} card is not in the synced catalogue',
      other: '{count} cards are not in the synced catalogue',
    },
    wrong_size_missing: 'A deck is {expected} cards: there are {total}, {diff} missing',
    wrong_size_excess: 'A deck is {expected} cards: there are {total}, {diff} too many',
    too_many_copies: '"{name}": {count} copies, the maximum is {max}',
    too_many_ace_spec: '{count} ACE SPEC cards: only {max} is allowed per deck',
    illegal_in_format: {
      one: '{count} card is not legal in {format}: {sample}',
      other: '{count} cards are not legal in {format}: {sample}',
    },
  },

  // … one namespace per component
}
```

`wrong_size` is one `ViolationCode` but two catalogue keys, because "3 missing" and "3 too many" are different sentences and no plural rule distinguishes them. Task 10 picks between them.

- [ ] **Step 3: Write `es.js` with exactly the same key set**

The Spanish that existed before the previous plan translated it away is the reference — recover it from git rather than re-inventing it:

```bash
git log --oneline --all -- frontend/src/components/DeckList.jsx
git show <commit-before-the-english-standard-plan>:frontend/src/components/DeckList.jsx
```

That copy was written for this app by the person who uses it. Retranslating from the English would lose the voice and, more concretely, would lose phrasings that were chosen to fit the width of a specific control.

- [ ] **Step 4: Prove the two key sets match**

```bash
cd frontend && node --input-type=module -e "
const flat = (o, p = '') => Object.entries(o).flatMap(([k, v]) =>
  v && typeof v === 'object' && !('one' in v)
    ? flat(v, p + k + '.')
    : [p + k])
const en = flat((await import('./src/i18n/en.js')).default)
const es = flat((await import('./src/i18n/es.js')).default)
const onlyEn = en.filter(k => !es.includes(k))
const onlyEs = es.filter(k => !en.includes(k))
console.log('only in en:', onlyEn)
console.log('only in es:', onlyEs)
"
```

The flag must come **before** `-e`; placed after, node treats it as a script argument and the
top-level `await import` fails. A plural entry counts as one key, not two — that is what the
`!('one' in v)` guard does.

Expected: both arrays empty. `onlyEs` non-empty is the worse failure — a key the fallback cannot cover.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/i18n/en.js frontend/src/i18n/es.js
git commit -m "feat: add the English source catalogue and its Spanish translation"
```

---

## Task 3: The React binding

**Files:**
- Create: `frontend/src/i18n/index.jsx`
- Modify: `frontend/src/main.jsx`

**Interfaces:**
- Consumes: `createTranslator` from Task 1; `en` and `es` from Task 2
- Produces:
  ```jsx
  <LocaleProvider>{children}</LocaleProvider>
  useT()      -> t                              // the translation function
  useLocale() -> { locale, setLocale }          // 'en' | 'es'
  ```
  Every later task uses `useT()`. Task 4 uses `useLocale()`.

**Written by the developer.** Context, lazy state initialisation and the effect that syncs `<html lang>` are the concepts here.

- [ ] **Step 1: Write `index.jsx`**

```jsx
import { createContext, useContext, useEffect, useMemo, useState } from 'react'

import en from './en.js'
import es from './es.js'
import { createTranslator } from './translate.js'

const CATALOGUES = { en, es }
const STORAGE_KEY = 'locale'

// A module-level variable would change the language without React ever knowing
// to re-render: nothing connects the mutation to the render. Context is the
// mechanism that turns "this value changed" into "the components reading it
// repaint".
const LocaleContext = createContext(null)

function detectLocale() {
  // …stored choice first, browser second. An explicit choice always outranks
  // detection — otherwise a Spanish browser would overrule the user every load.
}

export function LocaleProvider({ children }) {
  // …
}

export function useT() { /* … */ }
export function useLocale() { /* … */ }
```

The five things to get right:

1. **Lazy state initialisation.** `useState(detectLocale)` — passing the *function*, not `useState(detectLocale())`. The call form runs `localStorage.getItem` on every single render and throws the result away.
2. **The stored choice wins over `navigator.language`.** Read `localStorage` first; only fall back to `navigator.language.startsWith('es') ? 'es' : 'en'`.
3. **`localStorage` can throw.** Safari in private mode raises on `setItem`. Wrap reads and writes in `try/catch`; a failed persist must not take the app down, it must just not persist.
4. **Sync `<html lang>` in an effect.** `useEffect(() => { document.documentElement.lang = locale }, [locale])`. Writing to `document` during render is a side effect in the render phase, which React 19's Strict Mode will run twice. It is not decoration: a screen reader picks its voice from that attribute, and Spanish read with English phonetics is unintelligible.
5. **Memoise the context value.** `useMemo(() => ({ locale, setLocale, t }), [locale])` — a fresh object literal every render re-renders every consumer even when the locale did not change. `t` itself comes from `useMemo(() => createTranslator(CATALOGUES, locale), [locale])`.

One context carrying `{ locale, setLocale, t }` is correct here. Splitting it to narrow re-renders would optimise against what we want: on a language change, every consumer *should* repaint.

- [ ] **Step 2: Wrap the app**

```jsx
// frontend/src/main.jsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import App from './App.jsx'
import { LocaleProvider } from './i18n/index.jsx'
import './index.css'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <LocaleProvider>
      <App />
    </LocaleProvider>
  </StrictMode>,
)
```

Match the existing file's actual contents — the snippet above is the conventional shape, not necessarily what is on disk.

- [ ] **Step 3: Make `useT` fail loudly outside the provider**

```jsx
export function useT() {
  const ctx = useContext(LocaleContext)
  if (!ctx) throw new Error('useT must be used inside <LocaleProvider>')
  return ctx.t
}
```

Without the guard, a component rendered outside the provider gets `null`, and the error surfaces as `Cannot read properties of null` somewhere unrelated. Throwing at the boundary names the actual mistake.

- [ ] **Step 4: Verify in the browser console**

Start the app. Nothing visible changes yet — no component calls `t`. In the console:

```js
document.documentElement.lang            // 'es' on a Spanish browser, else 'en'
localStorage.getItem('locale')           // null — nothing chosen yet
```

Expected: `lang` reflects the browser; nothing is stored until a choice is made.

- [ ] **Step 5: Lint and build**

```bash
cd frontend && npm run lint && npm run build
```
Expected: both pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/i18n/index.jsx frontend/src/main.jsx
git commit -m "feat: bind the translator to React through a locale context"
```

---

## Task 4: The language switch

**Files:**
- Modify: `frontend/src/App.jsx` — the `<header>`
- Modify: `frontend/src/App.css`

**Interfaces:**
- Consumes: `useLocale()` from Task 3
- Produces: a visible control. No new module.

- [ ] **Step 1: Add the switch to the header**

```jsx
function LocaleSwitch() {
  const { locale, setLocale } = useLocale()

  return (
    <div className="locale-switch" role="group" aria-label="Language">
      {['en', 'es'].map((code) => (
        <button
          key={code}
          type="button"
          className={locale === code ? 'active' : ''}
          aria-pressed={locale === code}
          onClick={() => setLocale(code)}
        >
          {code.toUpperCase()}
        </button>
      ))}
    </div>
  )
}
```

Deliberately **not** the `Menu` component, despite the standing decision that every popover is a `Menu`: a popover for two options is more machinery than the job needs. If a third language arrives, that reverses.

`aria-pressed` rather than `aria-current`: these are toggle buttons, not navigation.

The `aria-label` and the `EN`/`ES` labels are the only strings in the app that are **not** translated. A language switch that renames itself in the language you cannot read is a switch you cannot find.

- [ ] **Step 2: Style it after the existing segmented controls**

Read `.view-switch` and `.deck-modes` in `App.css` and follow them — same border radius, same active treatment. This control should look like it was always there.

- [ ] **Step 3: Verify the switch works and persists**

- Click `ES`, then `EN`. Nothing on screen changes yet — no component calls `t`. That is expected at this task.
- After clicking: `localStorage.getItem('locale')` returns the chosen code.
- After clicking: `document.documentElement.lang` matches.
- Reload. The choice survives.
- `localStorage.removeItem('locale')` then reload: detection takes over again.

- [ ] **Step 4: Lint and build**

```bash
cd frontend && npm run lint && npm run build
```
Expected: both pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.jsx frontend/src/App.css
git commit -m "feat: add the EN/ES switch to the header"
```

---

## Task 5: Translate the shell — tabs and session types

The first task where the switch does something. Small on purpose: it proves the whole chain end to end before 15 components depend on it.

**Files:**
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/sessionTypes.js`
- Modify: every component that imports `TYPE_LABEL` (`SessionList.jsx`, `SessionDetail.jsx` — confirm with grep)

**Interfaces:**
- Consumes: `useT()` from Task 3; `nav.*` and `sessionType.*` from Task 2
- Produces: `SESSION_TYPES` exports values only. `TYPE_LABEL` is **removed** — a label that depends on the active locale cannot be a module constant. Consumers call `t('sessionType.' + value)`.

- [ ] **Step 1: Translate the tabs**

```jsx
const TABS = ['sessions', 'decks', 'cards']

// inside App(), after const t = useT()
{TABS.map((id) => (
  <button key={id} type="button" className={tab === id ? 'active' : ''} onClick={() => switchTab(id)}>
    {t(`nav.${id}`)}
  </button>
))}
```

The id was already the stable key and the label was already derived from it; dropping the `label` field just removes a copy.

- [ ] **Step 2: Strip the labels out of `sessionTypes.js`**

```js
/**
 * Session types, in a module of their own rather than inside a component.
 *
 * The reason is concrete, not stylistic: Vite hot-reloads a file only if it
 * exports components exclusively. Exporting constants too forces a full page
 * reload on every change and the state is lost.
 *
 * These values must match SessionType in backend/app/models/session.py. They are
 * wire values — never translate them. The human-readable label lives in the
 * catalogue under `sessionType.<value>`, because it changes with the locale and
 * a module constant cannot.
 */
export const SESSION_TYPES = ['league', 'cup', 'challenge', 'online', 'testing']
```

- [ ] **Step 3: Fix every `TYPE_LABEL` consumer**

```bash
grep -rn "TYPE_LABEL\|SESSION_TYPES" frontend/src
```

Each site becomes `t(\`sessionType.${value}\`)`. In `SessionDetail.jsx:195` the type sits in a `·`-separated header line — check the spacing survives.

- [ ] **Step 4: Verify both locales**

Start the app. Flip the switch on the sessions list.
Expected: the three tabs change language immediately, with no reload. The session-type labels on each row change with them. The URL and the selected tab do not change.

- [ ] **Step 5: Prove the wire values did not move**

Create a session with type "League" while the interface is in Spanish, then check what was stored:

```bash
curl -s localhost:8000/api/sessions | head -c 400
```

Expected: `"session_type": "league"` — the English wire value, regardless of the interface language. If it stored `"liga"`, a label leaked into the payload.

- [ ] **Step 6: Lint, test and build**

```bash
cd frontend && npm run lint && npm test && npm run build
```
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/App.jsx frontend/src/sessionTypes.js frontend/src/components/
git commit -m "feat: translate the tab bar and session type labels"
```

---

## Task 6: Translate the session screens

**Files:**
- Modify: `frontend/src/components/SessionList.jsx`, `SessionDetail.jsx`, `TagInput.jsx`, `PokemonPicker.jsx`, `PokemonPair.jsx`

**Interfaces:**
- Consumes: `useT()`; the `sessionList.*`, `sessionDetail.*`, `tagInput.*`, `pokemonPicker.*` namespaces from Task 2
- Produces: nothing new

- [ ] **Step 1: Thread `t` through the five components**

`const t = useT()` at the top of each component, then replace every literal. Includes `placeholder` and `aria-label` attributes — `SessionList.jsx:271` builds an `aria-label` by template (`Actions for {name}`), which becomes `t('sessionList.rowActions', { name: s.name || s.played_at })`.

- [ ] **Step 2: Leave these alone**

- `SessionList.jsx:20` — `toLocaleDateString('en-CA')`. Not display formatting. It produces `YYYY-MM-DD` for `<input type="date">`.
- `{s.played_at}` and `{session.played_at}` — raw dates. Localising them is a non-goal of this spec.
- `placeholder="League Cup Guadalajara"` and `placeholder="Gardevoir ex"` — example values, and proper nouns in both languages. Judgement call: keep them literal, and note the decision in the commit message.

- [ ] **Step 3: Verify both locales on both screens**

- Sessions list: heading, the new-session form's labels and placeholders, the empty state, the row menus.
- Session detail: the header line, the round form, the tag input, the Pokémon picker, the delete confirmation.

Expected: nothing in the wrong language, nothing showing a raw key like `sessionList.empty`, and the console free of `[i18n] missing` warnings.

- [ ] **Step 4: Lint, test and build**

```bash
cd frontend && npm run lint && npm test && npm run build
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/
git commit -m "feat: translate the session list and detail screens"
```

---

## Task 7: Translate the deck screens

The largest task in this plan. `DeckList.jsx` (576 lines) and `DeckBuilder.jsx` (488) carry most of the interface copy in the app.

**Files:**
- Modify: `frontend/src/components/DeckList.jsx`, `DeckGrid.jsx`, `DeckScreen.jsx`, `DeckBuilder.jsx`, `DeckCardList.jsx`, `DeckStats.jsx`

**Interfaces:**
- Consumes: `useT()`; the `deckList.*`, `deckGrid.*`, `deckScreen.*`, `deckBuilder.*`, `deckStats.*` namespaces from Task 2
- Produces: nothing new. `DeckValidation.jsx` is Task 10 — it needs the backend change first.

- [ ] **Step 1: Convert the two plurals to catalogue entries**

The previous plan turned these into whole words on both branches. Now they become one key each:

```jsx
// DeckList.jsx — was: `${deckCount} ${deckCount === 1 ? 'deck' : 'decks'}`
t('deckList.inside', { count: deckCount })

// DeckStats.jsx — was: two ternaries around 'session'/'sessions'
t('deckStats.played', { count: stats.sessions_counted, games: overall.played })
```

`deckStats.played` needs both numbers, and only one of them drives the plural — `count` selects the form, `games` is interpolated:

```js
played: {
  one: '{games} games across {count} session',
  other: '{games} games across {count} sessions',
}
```

- [ ] **Step 2: Thread `t` through the six components**

Includes the import/export dialog in `DeckList.jsx`, the version list and card-size menu in `DeckBuilder.jsx`, and the explanatory paragraphs in `DeckStats.jsx`.

- [ ] **Step 3: Leave these alone**

- `DeckList.jsx:513` — the PTCG Live placeholder (`'Pokémon: 17\n3 Riolu PRE 50\n…'`). Interop format, not prose.
- `placeholder="Mega Lucario"` — an example card name.
- Card names, set codes and format names rendered from data.
- The import report's numbers come from the backend; only the words around them are translated.

- [ ] **Step 4: Verify both locales**

- Decks list in grid and list view, at the root and inside a folder; the breadcrumb; the empty states for both "no decks" and "empty folder"; the folder deck counts at 0, 1 and several.
- Import a PTCG Live list and read the report in both languages.
- Deck builder: the toolbar, the card-size menu, the version list, the unsaved-changes state.
- Deck stats: the summary line at 1 session and at several; the dimmed-rows explanation; the empty state.

Expected: correct plurals at 0, 1 and n, in both languages, and no `[i18n] missing` in the console.

- [ ] **Step 5: Lint, test and build**

```bash
cd frontend && npm run lint && npm test && npm run build
```
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/
git commit -m "feat: translate the deck list, builder and stats screens"
```

---

## Task 8: Translate the card screens and the shared menu

**Files:**
- Modify: `frontend/src/components/CardSearch.jsx`, `CardDetail.jsx`, `Menu.jsx`

**Interfaces:**
- Consumes: `useT()`; the `cardSearch.*`, `cardDetail.*`, `menu.*` namespaces from Task 2
- Produces: nothing new

- [ ] **Step 1: Thread `t` through the three components**

`Menu.jsx` is shared by every screen. Check whether it renders any copy of its own (a trigger `aria-label`, a "no options" state) or only what callers pass in — if it only forwards, it may need no change at all, and that is a finding worth stating rather than a file to edit for its own sake.

- [ ] **Step 2: Leave the card data alone**

Card names, set names, rarity, types, attack names and attack text all come from TCGdex in English. They are data, and translating them is an explicit non-goal.

- [ ] **Step 3: Verify both locales**

Card search: the heading, the search field's placeholder, the filters, the empty state, the loading state, and the "no results" state. Open a card's detail in both languages — the chrome changes, the card's own text does not.

- [ ] **Step 4: Lint, test and build**

```bash
cd frontend && npm run lint && npm test && npm run build
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/
git commit -m "feat: translate the card search and detail screens"
```

---

## Task 9: Make `Violation` carry a code and parameters

The backend stops deciding words. This is the contract change the spec argues for, and `ViolationCode`'s own docstring says it was put there for exactly this.

**Files:**
- Modify: `backend/app/models/deck.py` — the `Violation` model
- Modify: `backend/app/services/deck_rules.py` — five construction sites
- Modify: `docs/api.md`

**Interfaces:**
- Consumes: nothing
- Produces: `Violation(code, params, card_ids)`. `message` is **removed**. Task 10 renders from `code` + `params`.

  | `code` | `params` |
  | --- | --- |
  | `unknown_card` | `count` |
  | `wrong_size` | `expected`, `total`, `diff` |
  | `too_many_copies` | `name`, `count`, `max` |
  | `too_many_ace_spec` | `count`, `max` |
  | `illegal_in_format` | `count`, `format`, `sample` |

- [ ] **Step 1: Change the model**

```python
class Violation(BaseModel):
    code: ViolationCode
    # The words live in the client's catalogue; this carries only the numbers and
    # names they need. Keeping a rendered `message` here too would be two sources
    # of truth for one sentence, and the day the Spanish changes and this does
    # not, nobody notices.
    params: dict[str, str | int] = Field(default_factory=dict)
    # Cards involved, so the interface can point at them.
    card_ids: list[str] = Field(default_factory=list)
```

- [ ] **Step 2: Convert the five construction sites**

```python
# unknown card
Violation(code=ViolationCode.UNKNOWN_CARD, params={"count": len(unknown)}, card_ids=unknown)

# size — `diff` is unsigned; the client picks "missing" or "too many" by comparing
Violation(
    code=ViolationCode.WRONG_SIZE,
    params={"expected": DECK_SIZE, "total": total, "diff": abs(DECK_SIZE - total)},
)

# copies per name
Violation(
    code=ViolationCode.TOO_MANY_COPIES,
    params={"name": name, "count": n, "max": MAX_COPIES_PER_NAME},
    card_ids=ids_by_name[name],
)

# ACE SPEC
Violation(
    code=ViolationCode.TOO_MANY_ACE_SPEC,
    params={"count": ace_total, "max": MAX_ACE_SPEC},
    card_ids=ace_ids,
)

# format legality
Violation(
    code=ViolationCode.ILLEGAL_IN_FORMAT,
    params={"count": len(illegal), "format": deck_format.value, "sample": sample},
    card_ids=illegal,
)
```

The local `detail`/`missing` variables that built the Spanish size sentence disappear — that string no longer exists on this side. `sample` (up to three card names joined with `, ` plus an ellipsis) survives as a parameter: those are English card names, which is data.

- [ ] **Step 3: Confirm nothing else read `message`**

```bash
grep -rn "\.message\|message=" backend/app frontend/src
```

Expected: no hit refers to a `Violation`. `DeckValidation.jsx` still renders `v.message` at this point — that is Task 10, and it is why the two tasks must land close together.

- [ ] **Step 4: Provoke each violation and read the JSON**

```bash
curl -s "localhost:8000/api/decks/<id>/validation" | python3 -m json.tool
```

Build a deck that trips each rule in turn — five copies of one card, 59 cards, two ACE SPEC, a card illegal in the declared format — and confirm each response carries the right `code` and a complete `params`. A missing parameter renders as a literal `{max}` on screen, which is exactly why Task 1 leaves it visible.

- [ ] **Step 5: Update `docs/api.md`**

The validation response shape changed. Document `code` + `params` and state that `message` is gone, with the reason: the words belong to the client.

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/deck.py backend/app/services/deck_rules.py docs/api.md
git commit -m "feat: send violation codes and parameters instead of prose"
```

---

## Task 10: Render violations from the catalogue

**Files:**
- Modify: `frontend/src/components/DeckValidation.jsx`

**Interfaces:**
- Consumes: `useT()`; `violation.*` from Task 2; the `params` contract from Task 9
- Produces: nothing new

- [ ] **Step 1: Render each violation through `t`**

```jsx
// One ViolationCode, two catalogue keys: "3 missing" and "3 too many" are
// different sentences and no plural rule tells them apart.
function violationKey(v) {
  if (v.code === 'wrong_size') {
    return v.params.total < v.params.expected
      ? 'violation.wrong_size_missing'
      : 'violation.wrong_size_excess'
  }
  return `violation.${v.code}`
}

// …inside the component
<li key={`${v.code}-${i}`}>{t(violationKey(v), v.params)}</li>
```

`v.params` is passed straight through — the backend already names `count` where a plural is needed, so no adaptation layer is required. This is why the parameter names in Task 9 were chosen to match the catalogue's.

- [ ] **Step 2: Translate the rest of the component**

The counter's verdict line — `Unchecked — save to validate`, `Legal deck`, `Not legal yet` — and the `aria-hidden` bar needs nothing.

- [ ] **Step 3: Verify every violation in both locales**

Trip each of the five rules and read the message in English and then in Spanish. Check specifically:
- `unknown_card` and `illegal_in_format` at exactly 1 and at several — these are plural entries, and Spanish changes the verb (`no está` → `no están`), not just the noun.
- `wrong_size` both under and over 60.
- `too_many_copies` shows the card name with straight quotes in English and `«…»` in Spanish, if that is how the Spanish catalogue words it.
- The unsaved-changes state still replaces the verdict rather than asserting legality.

- [ ] **Step 4: Lint, test and build**

```bash
cd frontend && npm run lint && npm test && npm run build
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/DeckValidation.jsx
git commit -m "feat: render deck violations from the message catalogue"
```

---

## Task 11: Sweep, document, and close

**Files:**
- Modify: `docs/architecture.md` — the `i18n/` module and the dependency direction
- Modify: `docs/operations.md` — `npm test` now exists
- Modify: `CLAUDE.md` — the conventions list

**Interfaces:**
- Consumes: everything
- Produces: a repository whose map matches it

- [ ] **Step 1: Find every string that never made it into the catalogue**

```bash
cd frontend/src
grep -rnoE ">[^<>{}]*[A-Za-z]{3,}[^<>{}]*<" App.jsx components/ | grep -vE "\{|\}"
grep -rnoE "(placeholder|aria-label|title)=\"[^\"]+\"" App.jsx components/
```

Every remaining literal must be a documented exclusion: the `EN`/`ES` switch, example placeholders, the PTCG Live format, card data. Anything else is a miss.

- [ ] **Step 2: Exercise the missing-key path on purpose**

Temporarily delete one key from `es.js` and load the app in Spanish.
Expected: the English text appears in its place and no warning fires (the fallback succeeded — this is the designed behaviour, not a failure).

Then reference a key that exists in neither catalogue from any component.
Expected: the raw key renders and `[i18n] missing "…" (es)` appears in the console exactly once per render.

Revert both changes.

- [ ] **Step 3: Verify the first-visit paths**

- `localStorage.removeItem('locale')`, set the browser to Spanish, reload → Spanish.
- `localStorage.removeItem('locale')`, set the browser to English (or any non-`es` language), reload → English.
- Choose the opposite language, reload → the choice holds, detection does not override it.
- Open a private window with `localStorage` blocked → the app loads, the switch works for the session, nothing throws.

- [ ] **Step 4: Add the conventions to `CLAUDE.md`**

```markdown
- **User-visible text lives in `frontend/src/i18n/`, never in a component.** `en.js` is the
  source; `es.js` is the translation and may lag — a missing key falls back to English. `count`
  is a reserved parameter name: it is the only one that selects a plural form.
- **The backend does not send prose.** A `Violation` carries a code and parameters; the words
  are the client's.
```

- [ ] **Step 5: Update `docs/architecture.md` and `docs/operations.md`**

`architecture.md` gains the `i18n/` module and its place in the dependency direction: components → `i18n` → nothing. `translate.js` depends on neither React nor the catalogues, which is why it is testable.

`operations.md` gains `npm test` — and the fact that it runs on Node's built-in runner, so there is nothing to install.

- [ ] **Step 6: Full verification pass**

```bash
cd frontend && npm run lint && npm test && npm run build
```

Then, with the backend running, walk every screen in both languages: sessions list, session detail, decks list (grid and list, root and folder), deck builder, import/export, deck stats, card search, card detail. Flip the switch on each screen rather than only at the start — a component that reads `t` once and caches it will only show up that way.

Expected: no untranslated text, no raw keys, no `[i18n] missing` warnings, correct plurals at 0, 1 and n.

- [ ] **Step 7: Commit**

```bash
git add docs/ CLAUDE.md
git commit -m "docs: record the i18n module and its conventions"
```

- [ ] **Step 8: Write the learning-log entry**

Dispatch the `log-mentor` skill. The subagent never saw this session, so the dispatch prompt must carry what only exists here:

- The concepts: **message catalogue**, **fallback locale**, **interpolation**, **`Intl.PluralRules`**, **React Context as the mechanism that connects a value change to a re-render**, and **separating an error from its representation** (the `Violation` code-plus-params change).
- `t()` was split out of the Provider into `translate.js` **specifically so `node --test` could run it** without JSX, a build step or a test framework. That is the reason the file exists, and it is not in any diff.
- A plural entry reached without `params.count` returns the key instead of the object, because returning the object makes React throw `Objects are not valid as a React child` and blanks the screen. That failure mode was designed against, not discovered.
- `react-i18next` was considered and rejected — the reasoning is in the spec, and the entry should say adopting it later is the intended end state, not a reversal.
- The switch's own `EN`/`ES` labels are the only untranslated strings in the app, deliberately: a language switch that renames itself in the language you cannot read is a switch you cannot find.

---

## Done when

- `npm run lint`, `npm test` and `npm run build` all pass.
- Every screen reads correctly in both languages, with the switch flipped *on* that screen.
- Plurals are right at 0, 1 and n, in both languages, including the five violation messages.
- The choice survives a reload; a cleared `localStorage` falls back to browser detection.
- `document.documentElement.lang` tracks the active locale.
- No `[i18n] missing` warnings anywhere in a full walk of the app.
- `Violation` has no `message` field, and `docs/api.md` says so.
