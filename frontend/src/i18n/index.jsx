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
  // The stored choice outranks the browser: once someone has picked a
  // language, a browser set to Spanish must not overrule them on the next
  // load. Detection only runs the first time, before any choice exists.
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'en' || stored === 'es') return stored
  } catch {
    // Safari private mode (and some locked-down configurations) can throw on
    // read too. Falling through to detection is the correct behaviour, not
    // an error: it just means nothing usable was stored.
  }
  return navigator.language.startsWith('es') ? 'es' : 'en'
}

export function LocaleProvider({ children }) {
  // Pass the function itself, not the result of calling it. useState(detectLocale())
  // would run localStorage.getItem and the navigator check on every render,
  // just to throw the result away on all but the first — lazy initialisation
  // runs the initializer once, on mount only.
  const [locale, setLocaleState] = useState(detectLocale)

  function setLocale(next) {
    setLocaleState(next)
    try {
      localStorage.setItem(STORAGE_KEY, next)
    } catch {
      // A failed persist must not take the app down — it must just not
      // persist. The locale still changes for this session via state.
    }
  }

  // document.documentElement.lang is what a screen reader uses to choose
  // pronunciation rules; writing it here (not during render) keeps the
  // mutation out of the render phase, which React 19 Strict Mode
  // double-invokes and would otherwise flip the attribute twice per commit.
  useEffect(() => {
    document.documentElement.lang = locale
  }, [locale])

  const t = useMemo(() => createTranslator(CATALOGUES, locale), [locale])

  // Without this memo, every render of LocaleProvider (triggered by anything,
  // not just a locale change) would hand consumers a new object and force
  // them all to re-render regardless of whether locale actually changed.
  const value = useMemo(() => ({ locale, setLocale, t }), [locale])

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>
}

export function useT() {
  const ctx = useContext(LocaleContext)
  // Without this guard, a component rendered outside the provider gets null
  // and the crash is "Cannot read properties of null" at the call site of
  // t(), far from the actual mistake — a missing <LocaleProvider>.
  if (!ctx) throw new Error('useT must be used inside <LocaleProvider>')
  return ctx.t
}

export function useLocale() {
  const ctx = useContext(LocaleContext)
  if (!ctx) throw new Error('useLocale must be used inside <LocaleProvider>')
  return { locale: ctx.locale, setLocale: ctx.setLocale }
}
