# React Context for Locale Management

> **Stack:** React · **Introduced in:** feat/i18n-locale-switch · **Date:** 2026-08-29

## Definition

**React Context** is a mechanism that connects a value change to a re-render: it provides a value to all descendants of a Provider component, and when the value changes, every component consuming it re-renders.

## Why it exists

A module-level variable would hold the current locale, but React has no way to know it changed. The component tree would not repaint — the function components would run with the old value still in their closure. Context is the bridge between "the value changed" and "the components reading it re-render."

For locale selection, this is essential: switching languages must repaint every component that calls `t()`, because every string on screen should change. A module variable would hide the change. Context makes it automatic.

## How it works

Context is built from three pieces:

1. **Create the context object** with an initial shape. This is just a container; the value is provided by a Provider component higher in the tree.

2. **A Provider component** that holds the state and passes it through `value=`. When `value` changes, React marks all descendant consumers for re-render.

3. **Consumers** that call `useContext()` to read the value. They only re-render if the context value object itself changed (by reference). Wrapping the value in `useMemo()` so a re-render of the Provider does not create a new object and force unnecessary downstream re-renders is a standard optimization.

The pattern, in miniature:

```javascript
// Create the context with a default (null is a marker for "not provided")
const ThemeContext = createContext(null)

// The Provider holds state and provides it
function ThemeProvider({ children }) {
  const [theme, setTheme] = useState('light')
  const value = useMemo(() => ({ theme, setTheme }), [theme])
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

// Consumers read from the context
function MyButton() {
  const { theme } = useContext(ThemeContext)
  return <button className={theme}>Click me</button>
}
```

One context carrying multiple fields (`{ locale, setLocale, t }`) is correct when they belong together — changing the locale invalidates the translator, so both must re-render together. Splitting them into separate contexts would optimize for the wrong problem: narrowing re-renders when the thing you want is for *every* consumer to repaint.

## In this project

The LocaleProvider lives in `frontend/src/i18n/index.jsx` and carries three pieces:

- `locale`: the current language (`'en'` or `'es'`)
- `setLocale()`: a function to change the language and persist it to `localStorage`
- `t()`: the translation function, rebuilt when the locale changes

```javascript
// frontend/src/i18n/index.jsx
const LocaleContext = createContext(null)
const STORAGE_KEY = 'locale'

function detectLocale() {
  // The stored choice outranks the browser: once someone has picked a
  // language, a browser set to Spanish must not overrule them on the next
  // load. Detection only runs the first time, before any choice exists.
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'en' || stored === 'es') return stored
  } catch {
    // Safari private mode can throw on localStorage access; fall through.
  }
  return navigator.language.startsWith('es') ? 'es' : 'en'
}

export function LocaleProvider({ children }) {
  // Lazy initialization: detectLocale() runs once, on mount.
  const [locale, setLocaleState] = useState(detectLocale)

  function setLocale(next) {
    setLocaleState(next)
    try {
      localStorage.setItem(STORAGE_KEY, next)
    } catch {
      // Persist failure must not break the app. The locale changes for
      // this session via state; just doesn't survive a reload.
    }
  }

  // Set the HTML lang attribute for screen readers.
  // Writing it in useEffect keeps the mutation out of render — React 19
  // Strict Mode double-invokes render functions.
  useEffect(() => {
    document.documentElement.lang = locale
  }, [locale])

  // Rebuild the translator when locale changes. onMissing warns only in
  // development — translate.js can't check import.meta.env itself without
  // coupling the framework-free core to Vite, so the check lives here.
  const t = useMemo(
    () =>
      createTranslator(CATALOGUES, locale, {
        onMissing: import.meta.env.DEV
          ? (key, loc) => console.warn(`[i18n] missing "${key}" (${loc})`)
          : () => {},
      }),
    [locale],
  )

  // Wrap in useMemo so a re-render of LocaleProvider (from any ancestor)
  // does not create a new value object and force consumers to re-render
  // even though locale didn't actually change.
  const value = useMemo(() => ({ locale, setLocale, t }), [locale, t])

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>
}

export function useT() {
  const ctx = useContext(LocaleContext)
  if (!ctx) throw new Error('useT must be used inside <LocaleProvider>')
  return ctx.t
}

export function useLocale() {
  const ctx = useContext(LocaleContext)
  if (!ctx) throw new Error('useLocale must be used inside <LocaleProvider>')
  return { locale: ctx.locale, setLocale: ctx.setLocale }
}
```

Wrapped at the top level:

```javascript
// frontend/src/main.jsx
import { LocaleProvider } from './i18n/index.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <LocaleProvider>
      <App />
    </LocaleProvider>
  </StrictMode>,
)
```

## Gotchas

**useContext outside a Provider throws.** If a component calls `useT()` but the Provider has not mounted yet (or was unmounted), `useContext()` returns `null` and the code crashes with "Cannot read properties of null". The guard clause in the hook catches this: it throws a clear error naming the missing Provider, not `null.t`.

**Creating a new context value object on every render forces re-renders.** If the Provider renders without the `value` being memoized, every child consumer re-renders even though nothing changed. This pattern is wrong:

```javascript
// WRONG: a new object on every render
<LocaleContext.Provider value={{ locale, setLocale, t }}>
```

Correct:

```javascript
// RIGHT: value only changes if locale or t changes
const value = useMemo(() => ({ locale, setLocale, t }), [locale, t])
<LocaleContext.Provider value={value}>
```

**Module-level state won't trigger re-renders.** If you try to skip Context and use a module variable instead:

```javascript
// WRONG: React never knows this changed
let currentLocale = 'en'
function setLocale(next) { currentLocale = next }
```

Components can read `currentLocale`, but React never knows to re-render them when it changes. Context is not optional for this problem — it is the only way to connect a state change to a repaint.

**Lazy initialization runs once.** Passing a function to `useState` instead of a value:

```javascript
// Correct: detectLocale() runs once, on mount
const [locale, setLocaleState] = useState(detectLocale)

// WRONG: detectLocale() runs on every render, just to throw the result away
const [locale, setLocaleState] = useState(detectLocale())
```

With lazy initialization, expensive initialization (reading localStorage, browser API calls) happens once. Without it, the initializer runs and is thrown away on every render.

## Related concepts

Context provides the *mechanism* for state changes to trigger re-renders. The *data* it carries (the message catalogue and plural selection logic) is built elsewhere, in entry 25. Error representation with codes and parameters, which consumes the `t()` function from Context, is in entry 27.

## References

- [useContext](https://react.dev/reference/react/useContext) — how to consume a context value
- [createContext](https://react.dev/reference/react/createContext) — how to create a context
- [Context in React](https://react.dev/learn/passing-data-deeply-with-context) — why context exists and when to use it
- [useMemo](https://react.dev/reference/react/useMemo) — preventing unnecessary re-renders by memoizing values
