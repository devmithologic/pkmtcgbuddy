# Worked example

This is a complete `log_mentor/` entry, shown as the calibration target for length, depth, and voice.
It would be saved as `log_mentor/03_HTTP_CORS_PREFLIGHT.md`.

Note what it does: defines the term before showing our code, explains the *browser's* behaviour rather
than just the fix, quotes the actual error string the developer would see, and links two primary
sources. Note what it doesn't do: narrate the session, apologise, or celebrate.

---

# CORS and the Preflight Request

> **Stack:** HTTP · **Introduced in:** wiring the React match form to `POST /api/matches` · **Date:** 2026-08-07

## Definition

**CORS** (Cross-Origin Resource Sharing) is an HTTP mechanism that lets a server declare which other
origins are allowed to read its responses. A **preflight request** is the automatic `OPTIONS` request a
browser sends ahead of certain cross-origin calls to ask for that permission first.

## Why it exists

Browsers enforce the **same-origin policy**: JavaScript on `http://localhost:5173` may not read a
response from `http://localhost:8000`, because origin is scheme + host + port and those differ on the
port. Without this rule, any page you visited could issue authenticated requests to your bank and read
the answers.

CORS is the server's way of opting out of that restriction for specific callers. Note the direction:
permission is granted by the *server being called*, and enforced by the *browser*. `curl` and the
FastAPI docs page never fail, because neither is a browser — which is exactly why this bug looks
mysterious when the same endpoint works from the terminal.

## How it works

For a "simple" request (`GET`, or `POST` with a form-ish content type), the browser sends the request,
then checks the response for `Access-Control-Allow-Origin`. If it's absent or doesn't match, the
response is discarded before your `fetch()` ever sees it.

A `POST` with `Content-Type: application/json` is **not** simple, so the browser preflights:

1. Browser sends `OPTIONS /api/matches` with `Origin: http://localhost:5173`,
   `Access-Control-Request-Method: POST`, `Access-Control-Request-Headers: content-type`.
2. Server answers `200` with `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`,
   `Access-Control-Allow-Headers`.
3. Only if the answer covers what was asked does the browser send the real `POST`.

The preflight result is cached for `Access-Control-Max-Age` seconds, so you'll see the `OPTIONS` once,
not on every keystroke.

## In this project

```python
# backend/app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # the Vite dev server, exactly — scheme + host + port
    allow_credentials=True,
    allow_methods=["*"],                      # covers the preflight's Access-Control-Request-Method
    allow_headers=["*"],                      # covers Content-Type: application/json
)
```

`add_middleware` registers **middleware** — a layer that wraps every request and response. It runs
before our route functions and can answer the `OPTIONS` preflight itself, which is why we never write
an `OPTIONS` handler. Middleware ordering matters in general; CORS is conventionally added first so it
also wraps error responses.

## Gotchas

- **The error names the wrong culprit.** The console says
  `Access to fetch at 'http://localhost:8000/api/matches' from origin 'http://localhost:5173' has been
  blocked by CORS policy: Response to preflight request doesn't pass access control check.` The backend
  logs a perfectly normal `200 OK` for the `OPTIONS`. Nothing is broken server-side; the browser is
  refusing to hand you the result.
- **A trailing slash breaks the origin match.** `"http://localhost:5173/"` is not the origin
  `http://localhost:5173`. Origins have no path.
- **`allow_origins=["*"]` and `allow_credentials=True` are mutually exclusive** per spec — the browser
  rejects a wildcard when credentials are involved. Listing the origin explicitly, as above, avoids the
  trap and is what production needs anyway.
- **CORS is not authorization.** It stops *other websites' JavaScript* from reading your responses. It
  stops nothing else. Anyone can still call the endpoint directly.

## Related concepts

Same-origin policy; **middleware** as a general request-pipeline pattern (the same idea appears in
Express and Django); simple vs. preflighted requests; `SameSite` cookies.

## References

- [CORS (FastAPI documentation)](https://fastapi.tiangolo.com/tutorial/cors/) — `CORSMiddleware` options and defaults
- [Cross-Origin Resource Sharing (MDN)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS) — the mechanism, header by header, from the browser's side
