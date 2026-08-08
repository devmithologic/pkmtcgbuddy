# useEffect: Dependencies, Cleanup, and StrictMode

> **Stack:** REACT · **Introduced in:** first vertical slice — loading matches in `App.jsx` · **Date:** 2026-08-08

## Definition

`useEffect` runs code **after** a render, to synchronise a component with something outside React — a
network request, a subscription, a timer, the DOM. Its second argument, the **dependency array**,
decides when it runs again; the function it returns is the **cleanup**, which undoes what the effect
set up.

## Why it exists

Rendering in React must be pure: given the same props and state, a component returns the same output
and changes nothing else. Fetching inside the render body breaks that — it fires on every render,
including the ones React performs speculatively.

Effects are the sanctioned escape hatch. The mental model in the official docs is worth adopting
literally: an effect is not "code that runs on mount", it is **synchronisation with an external
system**. That reframing is what makes the cleanup function obvious rather than an afterthought.

## How it works

The dependency array has three distinct forms:

```javascript
useEffect(() => { /* ... */ })          // after EVERY render
useEffect(() => { /* ... */ }, [])      // once, after the first render
useEffect(() => { /* ... */ }, [a, b])  // first render, and whenever a or b changed
```

Omitting the array while the effect calls `setState` is an infinite loop: the effect runs, state
changes, that triggers a render, which runs the effect again. In a data-fetching effect this means a
request storm against your own API.

React compares dependencies with `Object.is`. Objects and arrays created during render are new
references every time, so they never compare equal and defeat the check — a common source of effects
that "run constantly for no reason".

The returned function is the cleanup. React calls it **before each re-run** of the effect and once when
the component unmounts:

```javascript
useEffect(() => {
  const connection = createConnection(roomId)
  connection.connect()
  return () => connection.disconnect()   // cleanup
}, [roomId])
```

**StrictMode** makes missing cleanup impossible to ignore. In development only, React mounts each
component, unmounts it, and mounts it again — running one extra setup→cleanup→setup cycle. The
official framing: the goal is not "run this once", it is "make the effect correct when it runs twice".
If setup and cleanup mirror each other, the user cannot tell the difference. If they do not, the double
run exposes the leak now instead of in production.

This is why every network request in development appears twice in the Network tab. It is not a bug, and
suppressing it with a module-level `hasRun` flag hides the very problem StrictMode is pointing at.

## In this project

```jsx
// frontend/src/App.jsx
useEffect(() => {
  let active = true

  listMatches()
    .then((data) => { if (active) setMatches(data) })
    .catch((err) => { if (active) setError(err.message) })
    .finally(() => { if (active) setLoading(false) })

  return () => { active = false }
}, [])
```

The `active` flag is the cleanup for an in-flight request. A promise cannot be un-started, so instead
the effect marks its result as no longer wanted. Without it, a response arriving after the component
unmounted would call `setMatches` on something that no longer exists.

Under StrictMode the sequence is: effect runs, cleanup sets `active = false`, effect runs again with a
fresh `active`. The first response is discarded, the second is applied. Exactly one render results —
indistinguishable from production, which is the standard the docs set.

The empty array is correct here because the effect depends on nothing: it always loads the same list. In
phase 4, filtering by deck version would put that filter in the array, so changing it re-fetches.

Creating a match does **not** go through an effect:

```jsx
function handleCreated(match) {
  setMatches((previous) => [match, ...previous])
}
```

The `POST` already returned the created object with its real `id`, so the list is updated directly.
Re-fetching would spend a round trip retrieving something already in hand. Effects are for
synchronisation, not for reacting to user events — that is what handlers are for.

## Gotchas

- **Two requests in development is expected.** Verify against a production build before treating it as a bug.
- **Missing the dependency array while calling `setState` is an infinite loop.** The symptom is the
  Network tab filling continuously.
- **Objects and arrays as dependencies break the comparison.** Depend on primitives, or memoise.
- **`async` cannot be applied to the effect function itself.** `useEffect(async () => ...)` returns a
  promise where React expects a cleanup function. Use `.then()`, or declare an inner `async` function
  and call it.
- **Lying about dependencies to avoid a re-run causes stale closures.** The effect keeps values from the
  render in which it was created. If a dependency is genuinely unwanted, the problem is the effect's
  shape, not the array.

## Related concepts

`see 05_JAVASCRIPT_FETCH_ERROR_HANDLING.md` for what `listMatches()` does on failure; controlled
components; lifting state up; `AbortController` as the stronger form of this cleanup; React Query and
similar libraries, which package this pattern — worth adopting only once the manual version is
understood.

## References

- [useEffect — React](https://react.dev/reference/react/useEffect) — parameters, dependency comparison, and the StrictMode caveat
- [Synchronizing with Effects — React](https://react.dev/learn/synchronizing-with-effects) — the "external system" model and why effects run twice in development
- [StrictMode — React](https://react.dev/reference/react/StrictMode) — the development-only checks and what each is designed to expose
