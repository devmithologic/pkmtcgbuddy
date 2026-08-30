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
function lookup(catalogue, key) {
  return key.split('.').reduce((node, segment) => {
    if (node === null || typeof node !== 'object') return undefined
    return node[segment]
  }, catalogue)
}

// Replaces {name} from params. An absent parameter is left visible on purpose:
// "{max}" on screen is a bug you notice, "undefined" is a bug you ship.
function interpolate(template, params) {
  return template.replace(/{(\w+)}/g, (placeholder, name) =>
    Object.hasOwn(params, name) ? params[name] : placeholder,
  )
}

export function createTranslator(catalogues, locale, { onMissing } = {}) {
  const report = onMissing ?? ((key, loc) => console.warn(`[i18n] missing "${key}" (${loc})`))

  // Intl.PluralRules construction does real work (loads CLDR plural data for
  // the locale); t() runs on every render of every component, so a rule
  // selector built once per locale beats one built on every call.
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
      // A plural entry ({ one, other, ... }) needs `count` to pick a category.
      // Without it there's no valid string to interpolate — return the key
      // rather than the object, which React would refuse to render.
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
