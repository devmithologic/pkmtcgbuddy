# Debouncing and Out-of-Order Responses

> **Stack:** REACT · **Introduced in:** card search — searching as the user types · **Date:** 2026-08-08

## Definition

**Debouncing** delays an action until a burst of events stops, so rapid input produces one call
instead of many. A **race condition** here is the separate problem that HTTP responses arrive in an
order unrelated to the order they were requested, so a slow early response can overwrite a fast later
one.

They are two distinct bugs. Debouncing reduces how many requests you send; it does not stop the
survivors from landing in the wrong order.

## Why they exist

Search-as-you-type creates both. Typing `pikachu` fires seven renders:

```
p → pi → pik → pika → pikac → pikach → pikachu
```

**Without debouncing**, that is seven requests where only the last one's result will ever be shown.
Six are pure waste — of the user's bandwidth, of the upstream API's quota, and of your rate limit.

**Without cancellation**, the requests are also in flight simultaneously and complete in whatever
order the network decides. If `pika` takes 800 ms and `pikachu` takes 200 ms:

```
t=0    request "pika"      sent
t=100  request "pikachu"   sent
t=300  response "pikachu"  arrives → setResults(correct)
t=800  response "pika"     arrives → setResults(stale)     ← the bug
```

The input reads `pikachu`, the results are for `pika`, and nothing in the code looks wrong. It is
intermittent, it depends on network timing, and it will not reproduce on a fast connection — which is
exactly why it survives to production.

## How it works

Both fixes live in the same effect, and both rely on the **cleanup function**: React runs it before
each re-execution of the effect and once on unmount.

```javascript
useEffect(() => {
  const controller = new AbortController()

  const timer = setTimeout(() => {
    fetch(url, { signal: controller.signal })
      .then(/* ... */)
  }, 350)

  return () => {
    clearTimeout(timer)   // debounce: cancel the pending call
    controller.abort()    // race:     cancel the in-flight call
  }
}, [query])
```

Reading it as a sequence makes the mechanism clear. Every keystroke changes `query`, so React runs the
cleanup and then the effect again. The cleanup kills the timer that had not fired yet, and aborts the
request that had. Only the effect from the final keystroke survives long enough to complete.

`AbortController` is a browser primitive, not a React one: `signal` is a standard `fetch` option, and
aborting rejects the promise with an `AbortError`.

Choosing the delay is a trade-off with no correct answer: too short and requests still pile up, too
long and the interface feels unresponsive. 300–400 ms is the usual range for a search field, because
it is roughly the gap between words when typing.

## In this project

```jsx
// frontend/src/components/CardSearch.jsx
const DEBOUNCE_MS = 350

useEffect(() => {
  if (!canSearch) { setResults([]); return }

  const controller = new AbortController()

  const timer = setTimeout(async () => {
    setLoading(true)
    try {
      const data = await searchCards({ ...filters, page }, controller.signal)
      setResults(data.cards)
    } catch (err) {
      if (err.name !== 'AbortError') setError(err.message)
    } finally {
      if (!controller.signal.aborted) setLoading(false)
    }
  }, DEBOUNCE_MS)

  return () => { clearTimeout(timer); controller.abort() }
}, [filters, page, canSearch])
```

Two details that are easy to get wrong:

**`if (err.name !== 'AbortError')`.** An abort rejects the promise, so it lands in `catch` alongside
real failures. Showing it would mean an error message flashing on every keystroke — the fix producing
a worse symptom than the bug.

**`if (!controller.signal.aborted) setLoading(false)`.** The `finally` of a cancelled request would
otherwise clear the spinner that the *newer* request just turned on, making the interface look idle
while it is still working.

The `signal` reaches `fetch` through the API layer, which is why `client.js` passes options through
rather than building them:

```javascript
// frontend/src/api/cards.js
export function searchCards(filters, signal) {
  return request(`/api/cards${queryString(filters)}`, { signal })
}
```

## Gotchas

- **Debouncing alone does not fix the race.** It makes it rarer, which is worse: the bug survives
  testing and appears for users on slow connections.
- **Forgetting `clearTimeout` in the cleanup** leaves every keystroke's timer alive. The debounce
  appears to work — one request per keystroke, just 350 ms late.
- **Cancelling is not free upstream.** The server may already have done the work; abort stops your
  client from waiting, not the backend from computing.
- **Do not debounce a submit button.** Debouncing is for continuous input. A click that must not
  double-fire needs a disabled button or throttling, which are different tools.
- **`AbortError` is not an error in your application's sense.** Treat it as control flow.

## Related concepts

`see 06_REACT_USEEFFECT_DEPENDENCIES.md` — the cleanup function this depends on; throttling (a rate
limit rather than a quiet-period trigger); `AbortSignal.timeout()` for deadlines;
`see 05_JAVASCRIPT_FETCH_ERROR_HANDLING.md` for why an abort rejects while a `500` does not.

## References

- [AbortController — MDN](https://developer.mozilla.org/en-US/docs/Web/API/AbortController) — the cancellation primitive and its `signal`
- [You Might Not Need an Effect — React](https://react.dev/learn/you-might-not-need-an-effect) — when fetching in an effect is right, and when it is not
- [Synchronizing with Effects — React](https://react.dev/learn/synchronizing-with-effects#fetching-data) — the official treatment of the race condition, including the ignore-flag alternative
