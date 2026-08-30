import assert from 'node:assert/strict'
import { test } from 'node:test'

import en from './en.js'
import es from './es.js'

// This test exists because translate.js's fallback to `en` is silent by
// design (see translate.js: the FALLBACK_LOCALE branch returns without ever
// calling `report`). A key added to en.js and forgotten in es.js degrades
// Spanish with no warning and no failing test — the page just shows English.
// Nothing else in the suite catches that; this file is the only thing that
// walks both catalogues and diffs them.

const PLURAL_CATEGORIES = new Set(['zero', 'one', 'two', 'few', 'many', 'other'])

// A node is a plural entry, not a namespace, when every one of its own keys is
// a CLDR plural category. Testing for `one` alone would misread a namespace
// that happened to contain a key called `one`.
function isPlural(v) {
  return (
    v !== null &&
    typeof v === 'object' &&
    Object.keys(v).length > 0 &&
    Object.keys(v).every((k) => PLURAL_CATEGORIES.has(k))
  )
}

// Walks to the leaves. A leaf is a string or a plural entry; anything else is
// a defect, and `null` is called out by name because `typeof null === 'object'`
// would otherwise let it pass as a namespace and later throw inside t().
function walk(node, path, locale, out, problems) {
  if (node === null) {
    problems.push(`${locale}: ${path} is null — translate.js would throw on it`)
    return
  }
  if (typeof node === 'string') {
    if (node.trim() === '') problems.push(`${locale}: ${path} is an empty string`)
    out.set(path, node)
    return
  }
  if (typeof node !== 'object') {
    problems.push(`${locale}: ${path} is a ${typeof node}, expected a string`)
    return
  }
  if (isPlural(node)) {
    if (!('one' in node)) problems.push(`${locale}: plural ${path} has no "one" branch`)
    if (!('other' in node)) problems.push(`${locale}: plural ${path} has no "other" branch`)
    for (const [cat, text] of Object.entries(node)) {
      if (typeof text !== 'string' || text.trim() === '')
        problems.push(`${locale}: plural ${path}.${cat} is not a non-empty string`)
    }
    out.set(path, node)
    return
  }
  for (const [k, v] of Object.entries(node)) walk(v, path ? `${path}.${k}` : k, locale, out, problems)
}

function leaves(catalogue, locale) {
  const out = new Map()
  const problems = []
  walk(catalogue, '', locale, out, problems)
  return { out, problems }
}

const placeholders = (v) =>
  new Set(
    (typeof v === 'string' ? [v] : Object.values(v))
      .flatMap((s) => [...s.matchAll(/{(\w+)}/g)].map((m) => m[1])),
  )

test('en and es catalogues have no null or empty leaves, and every plural has both branches', () => {
  const { problems: enProblems } = leaves(en, 'en')
  const { problems: esProblems } = leaves(es, 'es')
  assert.deepEqual(enProblems, [])
  assert.deepEqual(esProblems, [])
})

test('en and es catalogues have identical key sets', () => {
  // onlyEs is the worse failure of the two: the fallback chain cannot cover a
  // key that English lacks, so a request for it returns the raw key.
  const { out: enLeaves } = leaves(en, 'en')
  const { out: esLeaves } = leaves(es, 'es')
  const onlyEn = [...enLeaves.keys()].filter((k) => !esLeaves.has(k))
  const onlyEs = [...esLeaves.keys()].filter((k) => !enLeaves.has(k))
  assert.deepEqual(onlyEn, [], 'keys present only in en')
  assert.deepEqual(onlyEs, [], 'keys present only in es — NOT covered by the en fallback')
})

test('en and es agree on the placeholders each key interpolates', () => {
  // A translation that drops {count} silently renders a sentence missing its
  // number; one that invents {foo} renders a literal "{foo}" on screen.
  const { out: enLeaves } = leaves(en, 'en')
  const { out: esLeaves } = leaves(es, 'es')
  const problems = []
  for (const [key, enVal] of enLeaves) {
    const esVal = esLeaves.get(key)
    if (esVal === undefined) continue
    const a = placeholders(enVal)
    const b = placeholders(esVal)
    const missing = [...a].filter((p) => !b.has(p))
    const extra = [...b].filter((p) => !a.has(p))
    if (missing.length) problems.push(`${key}: es is missing placeholder(s) ${missing.join(', ')}`)
    if (extra.length) problems.push(`${key}: es has placeholder(s) en lacks: ${extra.join(', ')}`)
  }
  assert.deepEqual(problems, [])
})

test('a plural entry in one locale is a plural entry in the other', () => {
  // If en has an object and es a flat string (or vice versa), the count-bearing
  // sentence loses its agreement in half the app.
  const { out: enLeaves } = leaves(en, 'en')
  const { out: esLeaves } = leaves(es, 'es')
  const problems = []
  for (const [key, enVal] of enLeaves) {
    const esVal = esLeaves.get(key)
    if (esVal === undefined) continue
    const enPlural = typeof enVal !== 'string'
    const esPlural = typeof esVal !== 'string'
    if (enPlural !== esPlural)
      problems.push(`${key}: plural in ${enPlural ? 'en' : 'es'} but a flat string in the other`)
  }
  assert.deepEqual(problems, [])
})

test('en.js has no Spanish text leaking into the source catalogue', () => {
  // Pokémon, Poké Ball and Pokédex carry acute accents in English, so the
  // brand family is excluded before checking for stray accents or Spanish
  // punctuation.
  const { out: enLeaves } = leaves(en, 'en')
  const problems = []
  for (const [key, val] of enLeaves) {
    const text = typeof val === 'string' ? val : Object.values(val).join(' ')
    if (/[áéíóúñ¡¿«»]/i.test(text.replace(/Pok[eé][^\s]*/gi, '')))
      problems.push(`en: ${key} looks like Spanish: ${JSON.stringify(text).slice(0, 70)}`)
  }
  assert.deepEqual(problems, [])
})
