# Why `fetch` Does Not Throw on HTTP Errors

> **Stack:** JAVASCRIPT · **Introduced in:** first vertical slice — `src/api/matches.js` · **Date:** 2026-08-08

## Definition

`fetch()` returns a promise that **resolves** for any completed HTTP exchange, including `404` and
`500`. It rejects only when the exchange never completed — network failure, DNS error, CORS block,
aborted request. Detecting an error status is the caller's job, via `response.ok`.

## Why it exists

This surprises almost everyone, because it inverts the usual convention: in most HTTP libraries an
error status raises. `axios` rejects on `4xx`/`5xx`; Python's `requests` has `raise_for_status()`.

The Fetch Standard draws the line differently, and consistently: a `500` **is** a successful HTTP
transaction. The request was sent, the server answered, the response arrived intact. That the answer
reports a server-side problem is application semantics, not transport failure. `fetch` models the
transport.

The practical consequence is that the naive version compiles, runs, and is wrong:

```javascript
const matches = await fetch('/api/matches').then((r) => r.json())
// 500 -> r.json() throws "Unexpected token" on an HTML error page, or
// 422 -> matches is {detail: [...]}, an object where an array was expected
```

The failure surfaces later and elsewhere — `matches.map is not a function` in a component that is not
the problem. The `try/catch` around it appears to be correct error handling and catches nothing useful.

## How it works

`Response` exposes the status directly:

```javascript
const response = await fetch(url)

response.ok          // true for status 200-299
response.status      // 404
response.statusText  // "Not Found"
```

The standard shape is one wrapper that turns error statuses into exceptions, so callers can use a
single `try/catch` for both transport and application failures:

```javascript
async function request(url, options) {
  const response = await fetch(url, options)
  if (!response.ok) {
    throw new Error(await errorMessage(response))
  }
  return response.json()
}
```

Two details matter. `response.json()` is itself async, because the body arrives as a stream separate
from the headers — `fetch` resolves as soon as headers are available, which is why a slow body does not
delay status checks. And the body can be read **only once**; calling `.json()` after `.text()` on the
same response throws `TypeError: Body has already been consumed`.

## In this project

```javascript
// frontend/src/api/matches.js
async function request(path, options) {
  const response = await fetch(`${API_URL}${path}`, options)

  if (!response.ok) {
    throw new Error(await errorMessage(response))
  }

  return response.json()
}
```

`errorMessage` exists because FastAPI has two distinct error shapes, and a useful message requires
handling both:

```javascript
const body = await response.json()

// 422 validation: detail is an array of {loc, msg, type}
if (Array.isArray(body.detail)) {
  return body.detail.map((e) => `${e.loc?.join('.')}: ${e.msg}`).join(' · ')
}
// HTTPException: detail is a string
return body.detail ?? fallback
```

The whole thing sits inside `try/catch` with a status-line fallback, because an error response is not
guaranteed to be JSON at all — a crashed proxy returns HTML, and parsing it would throw *inside the
error handler*, replacing a useful message with a parse error.

Every component reaches the API through this module. When a request fails, the component gets an
`Error` with a readable message and renders it:

```jsx
// frontend/src/components/MatchForm.jsx
catch (err) {
  setError(err.message)
}
```

## Gotchas

- **`response.ok` is a range check, not a truthiness check.** It is `true` for `200`–`299`. A `304 Not
  Modified` is not `ok`, and a `201` is.
- **Redirects are followed silently by default.** `response.ok` may describe a different URL than the one
  requested; `response.url` and `response.redirected` say which.
- **The body streams only once.** Read it into a variable if you need it twice.
- **A CORS block rejects rather than resolves**, and the error object deliberately carries almost no
  detail — the browser will not leak cross-origin information to script. The real message is in the
  console, not in the exception.
- **`fetch` has no timeout.** A hung server leaves the promise pending indefinitely. `AbortSignal.timeout()`
  is the built-in remedy; not needed against localhost, essential against a third-party API — which is
  phase 3.

## Related concepts

`see 04_HTTP_CORS_PREFLIGHT.md` for the failure mode that rejects instead of resolving; HTTP status
semantics (`201` vs `200`, `422` vs `400`); `AbortController`; error boundaries in React.

## References

- [Response.ok — MDN](https://developer.mozilla.org/en-US/docs/Web/API/Response/ok) — the exact status range and its semantics
- [Using the Fetch API — MDN](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch) — includes the explicit warning that `fetch` does not reject on HTTP error status
- [Fetch Standard — WHATWG](https://fetch.spec.whatwg.org/) — the normative specification
