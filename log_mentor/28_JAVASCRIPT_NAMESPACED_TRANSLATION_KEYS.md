# Namespaced Translation Keys

> **Stack:** JavaScript · **Introduced in:** feat/i18n-locale-switch · **Date:** 2026-08-29

## Definition

**Namespaced keys** organize catalogue entries hierarchically: `violation.wrong_size_missing`, `cardCategory.Pokemon`, `deckStats.played`. Each namespace groups related strings and allows one key to resolve to different text in different languages, including differences in formatting that are not translations.

## Why it exists

An alternative is to use the English string itself as the key: `t("Maximum 4 copies of {name}")`. This breaks when translations need *formatting* differences that are not just word-for-word replacements.

**Example:** the card name "Iono" is a proper noun and does not translate, but the sentence around it does — and not just its words. In English it appears with straight quotes: `"Iono"`. In Spanish, typography conventions use angular quotes: `«Iono»`. A single source-string key cannot express this:

```javascript
// source-string key: WRONG
t('"Iono": 5 copies, the maximum is 4')
// Both languages would have to fit the same template; one language's
// quoting and grammar can't bend it to fit.

// namespaced key: CORRECT
// English: '"Iono": 5 copies, the maximum is 4'
// Spanish: '«Iono»: 5 copias, el máximo son 4'
// The catalogue controls both text and formatting per language.
```

The real strings sharpen the point beyond quoting: English says "the maximum **is** 4" (singular copula), Spanish says "el máximo **son** 4" (plural, agreeing with the count of cards, not the count "máximo"). A single source-string key could express neither the quote style nor the copula.

**Other reasons to namespace:**

1. **Searchability.** Grep for `violation\.` finds every error message in the codebase and catalogue.

2. **Locator stability.** If a message changes, the key stays the same. A source-string key changes when the English wording changes, breaking every reference to it.

3. **Reuse.** Several contexts might need the same word ("Session", "sessions"). Namespacing lets each context have its own entry: `nav.sessions` (the menu label), `deckStats.played` (statistics), `sessionType` (a category).

4. **Non-linguistic customization.** A company might want to call themselves "Team" instead of "League" without changing the source language.

## How it works

**Catalogue structure:** A deeply nested object where each level is a namespace.

```javascript
export default {
  nav: {
    sessions: 'Sessions',
    decks: 'Decks',
    cards: 'Cards'
  },
  
  violation: {
    wrong_size_missing: {
      one: 'A deck is {expected} cards: there are {total}, {count} missing',
      other: 'A deck is {expected} cards: there are {total}, {count} missing',
    },
    too_many_copies: '"{name}": {count} copies, the maximum is {max}'
  },
  
  cardCategory: {
    Pokemon: 'Pokémon',
    Trainer: 'Trainer',
    Energy: 'Energy'
  }
}
```

**Resolution:** The `lookup()` function walks a dotted key through the tree:

```javascript
function lookup(catalogue, key) {
  // 'violation.too_many_copies' → split to ['violation', 'too_many_copies']
  // → reduce through the tree: catalogue['violation']['too_many_copies']
  return key.split('.').reduce((node, segment) => {
    if (node === null || typeof node !== 'object') return undefined
    return node[segment]
  }, catalogue)
}

lookup(en, 'violation.too_many_copies')
// → '"{name}": {count} copies, the maximum is {max}'

lookup(es, 'violation.too_many_copies')
// → '«{name}»: {count} copias, el máximo son {max}'
```

**Multi-language example:** The same key resolves to a differently worded string, not a word-for-word swap:

```javascript
// frontend/src/i18n/en.js
cardDetail: {
  aceSpecNote: 'ACE SPEC — max 1 per deck'
}

// frontend/src/i18n/es.js
cardDetail: {
  aceSpecNote: 'ACE SPEC — máximo 1 por mazo'
}

// In both languages:
const aceSpecText = t('cardDetail.aceSpecNote')
// English: 'ACE SPEC — max 1 per deck'
// Spanish: 'ACE SPEC — máximo 1 por mazo'
```

## In this project

The entire UI is wired with namespaced keys. Examples:

```javascript
// frontend/src/components/DeckBuilder.jsx
// Namespace: deckBuilder.*
{t('deckBuilder.saveChanges')}
{dirty && <p className="hint">{t('deckBuilder.unsavedChanges')}</p>}

// frontend/src/components/DeckValidation.jsx
// Namespace: violation.*
// violationKey() picks between wrong_size_missing and wrong_size_excess —
// one ViolationCode, two catalogue keys, because no plural rule tells "3
// missing" apart from "3 too many".
{violations.map((v, i) => (
  <li key={`${v.code}-${i}`}>{t(violationKey(v), v.params)}</li>
))}

// frontend/src/components/SessionDetail.jsx
// Namespace: sessionType.*
<h2>{session.name || t(`sessionType.${session.session_type}`)}</h2>
```

The namespaces form an ontology of the app: `nav`, `common`, `sessionType`, `cardCategory`, `cardDetail`, `cardSearch`, `deckBuilder`, `deckStats`, `deckValidation`, `violation`, `deckCardList`, `pokemonPicker`, `menu`.

The catalogue is built once and is complete before the app runs. Adding a new feature includes adding its namespace to both `en.js` and `es.js`. The key never changes once created; if the English wording drifts, the catalogue updates but the code (`t('violation.wrong_size_missing')`) stays the same.

## Gotchas

**Typos in keys render the key, not an error.** If the code calls `t('violaton.wrong_size_missing')` (typo: "violaton"), the lookup misses, the fallback misses, and the screen shows `"violaton.wrong_size_missing"`. This is intentional — missing translations are visible, not silent. But it means code review and testing must verify keys are spelled correctly. An IDE plugin or a build-time check (via TypeScript or a custom linter) can catch this automatically.

**Moving a string to a different namespace breaks all references.** If `cardDetail.aceSpecNote` is renamed to `cardSearch.aceSpecNote`, every component calling it must update. Use a search-and-replace; a simple grep for `aceSpecNote` finds all the places.

**Shared strings mean duplication or under-organization.** The word "deck" appears in `deckBuilder.nameLabel` ('Deck name'), `deckValidation.legal` ('Legal deck'), and `deckStats.noData` ('...Log sessions with this deck...'). Tempting to extract it to `common.deck` and reuse. Resist this: what looks like the same word in one language may not be the same in another (gendered languages, different domains use different terms). Let duplication tell you when re-organization is needed.

**Backwards compatibility on key renames.** Unlike source-string keys, namespaced keys are stable across translations. If "Iono" is a proper noun in all languages, the Spanish catalogue can be updated from straight quotes to angular quotes without changing the key. But if the code is deployed before the catalogue, the new key is missing and renders as its own name.

## Related concepts

Namespaced keys are used throughout the i18n system. They are the *locators* for the **message catalogue** (entry 25) and the **error code and parameters** pattern (entry 27), where `violation.` prefixes tell the frontend which namespace to search.

## References

- [i18n best practices: key naming](https://www.w3.org/International/questions/qa-what-is-i18n) — WHATWG guidance on internationalization structure
- [Translation memory and terminology databases](https://en.wikipedia.org/wiki/Translation_memory) — how professional translators organize strings
- [Taxonomy and ontology in software](https://en.wikipedia.org/wiki/Ontology_(information_science)) — the design principle that namespaces embody
