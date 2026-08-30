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
