# Message Catalogue and Intl.PluralRules

> **Stack:** JavaScript · **Introduced in:** feat/i18n-locale-switch · **Date:** 2026-08-29

## Definition

A **message catalogue** is a nested object mapping dotted keys to translated strings, with support for plural forms selected by locale-specific grammar rules using the browser's `Intl.PluralRules` API.

## Why it exists

Hand-rolling plurals in code (suffixing a noun or branching on `if (count === 1)`) works for English but fails across languages. Spanish pluralizes on the same number as English, but Polish has three categories, and Arabic has six. Encoding grammar rules in code forces the developer to know every language's rules; storing plural forms as data in the catalogue and delegating selection to `Intl.PluralRules` makes a system that works everywhere a browser runs.

## How it works

**The catalogue shape:** A nested object where keys are dot-separated (`violation.wrong_size_missing`) and values are either strings or objects with plural forms.

```javascript
{
  violation: {
    wrong_size_missing: {
      one: 'A deck is {expected} cards: there are {total}, {count} missing',
      other: 'A deck is {expected} cards: there are {total}, {count} missing',
    },
    too_many_copies: '"{name}": {count} copies, the maximum is {max}'
  }
}
```

**The resolution chain:** Call `t(key, params)` — the translation function built from a catalogue. It:

1. Walks the dotted key into the current locale's catalogue (`en` or `es`).
2. On miss, falls back to the default locale (`en`). This is the **fallback locale** — it is always present, so missing a translation for one language does not break the feature.
3. On miss again, returns the key itself and warns in development. A missing translation must be visible to developers, not silently shipped to users.
4. If the resolved value is an object (a plural entry) and `params.count` is present:
   - Create a `new Intl.PluralRules(locale)` — a browser-native object that knows the grammar rules for that language.
   - Call `.select(params.count)` to pick the plural form (`'one'`, `'other'`, or language-specific categories like Polish's `'few'`).
   - Look up the selected form in the entry (falling back to `'other'` if the form is missing).
5. **Interpolate** placeholders: replace `{name}` from `params` in the string, leaving `{missing}` visible on screen so omissions are visible, not silently undefined.

**The critical design rule: `count` is reserved.** It is the only parameter that drives plural selection. Every independently-varying quantity needs its own catalogue entry. In `"1 games across 1 session"`, the game count and session count both varied independently, pluralizing on the session count alone — a sentence that reads wrong. The fix was two entries:

```javascript
deckStats: {
  played: {
    one: '{count} game',
    other: '{count} games'
  },
  playedAcross: {
    one: 'across {count} session',
    other: 'across {count} sessions'
  }
}
```

Then composed at the call site: `` {t('deckStats.played', {count: games})}{' '}{t('deckStats.playedAcross', {count: sessions})} ``. Two entries, each with one `count`, read correctly when rendered.

## In this project

The catalogue lives in `frontend/src/i18n/en.js` and `frontend/src/i18n/es.js` — deeply nested objects, one per locale. The translation function is built once per locale change in `frontend/src/i18n/index.jsx`:

```javascript
// frontend/src/i18n/translate.js
const FALLBACK_LOCALE = 'en'

function lookup(catalogue, key) {
  return key.split('.').reduce((node, segment) => {
    if (node === null || typeof node !== 'object') return undefined
    return node[segment]
  }, catalogue)
}

function interpolate(template, params) {
  return template.replace(/{(\w+)}/g, (placeholder, name) =>
    Object.hasOwn(params, name) ? params[name] : placeholder,
  )
}

export function createTranslator(catalogues, locale, { onMissing } = {}) {
  // The caller (frontend/src/i18n/index.jsx) supplies onMissing so the core
  // stays framework-free; the default here is what runs under `node --test`.
  const report = onMissing ?? ((key, loc) => console.warn(`[i18n] missing "${key}" (${loc})`))

  const pluralRules = new Map()
  function rulesFor(loc) {
    let rules = pluralRules.get(loc)
    if (!rules) {
      rules = new Intl.PluralRules(loc)
      pluralRules.set(loc, rules)
    }
    return rules
  }

  return function t(key, params = {}) {
    let entry = lookup(catalogues[locale], key)
    let resolvedLocale = locale
    if (entry === undefined) {
      entry = lookup(catalogues[FALLBACK_LOCALE], key)
      resolvedLocale = FALLBACK_LOCALE
    }
    if (entry === undefined) {
      report(key, locale)
      return key
    }

    if (typeof entry === 'object') {
      if (typeof params.count !== 'number') {
        report(key, locale)
        return key
      }
      const category = rulesFor(resolvedLocale).select(params.count)
      const template = entry[category] ?? entry.other
      return interpolate(template, params)
    }

    return interpolate(entry, params)
  }
}
```

Usage:

```javascript
// In a component
import { useT } from '../i18n/index.jsx'

export function DeckStats() {
  const t = useT()
  return <p>{t('deckStats.played', { count: gameCount })}</p>
}
```

## Gotchas

**A plural entry without `params.count` returns the key, not the object.** React throws "Objects are not valid as a React child" and blanks the entire screen. Returning the key makes the omission visible: `t('deckStats.played')` renders `"deckStats.played"` on screen, a bug the developer will see and fix immediately.

**Intl.PluralRules caching matters.** Creating a new `Intl.PluralRules(locale)` on every translation call loads CLDR data from the browser's tables. A translator built once per locale change and cached in a Map means plural selection is O(1) on every render, not O(CLDR).

**A missing form falls back to `'other'`.** If a catalogue entry has `{ one, other }` and the call site forgets to interpolate `{count}` on the second render, the code doesn't break — it renders the `'other'` form. This is a safety measure, not a feature to rely on.

**Fallback locale must be complete.** If `en.js` is missing a key, that key will be shown to users in English-speaking locales with no warning. The English catalogue should be the complete reference.

## Related concepts

The plural mechanism answers one half of the problem — selecting a form. The other half — how to render structured content like error messages — is solved in entry 27 (error codes and parameters). The **locale state** that feeds `t()` comes from React Context, described in entry 26.

## References

- [Intl.PluralRules](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/PluralRules) — MDN reference for plural form selection by locale
- [Intl.PluralRules.prototype.select()](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/PluralRules/select) — how to pick the correct plural form for a number
- [Internationalization patterns in the ECMAScript spec](https://tc39.es/ecma402/) — the plural categories for every language
