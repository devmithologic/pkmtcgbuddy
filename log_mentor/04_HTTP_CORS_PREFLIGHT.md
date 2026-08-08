# CORS and the Preflight Request

> **Stack:** HTTP · **Introduced in:** first vertical slice — connecting the React form to `POST /api/matches` · **Date:** 2026-08-08

## Definition

**CORS** (Cross-Origin Resource Sharing) is an HTTP mechanism by which a server declares which other
origins are allowed to read its responses. A **preflight request** is the automatic `OPTIONS` request a
browser sends ahead of certain cross-origin calls to obtain that permission first.

## Why it exists

Browsers enforce the **same-origin policy**. An origin is the triple *scheme + host + port*, so
`http://localhost:5173` and `http://localhost:8000` are different origins — same host, different port.
By default, JavaScript served from one may not read responses from the other.

The reason is credentials. Browsers attach cookies automatically by origin. Without the same-origin
policy, any page you visited could issue authenticated requests to your bank in the background and read
the replies.

CORS is how a server opts out of that restriction for specific callers. Note the direction carefully:
permission is granted by the *server being called*, and enforced by the *browser*. `curl` and the
FastAPI `/docs` page never fail, because neither is a browser. That asymmetry is what makes the bug
confusing — the endpoint demonstrably works from the terminal while the app cannot reach it.

## How it works

For a **simple request** — `GET`, or `POST` with a form-style content type — the browser sends the
request, then inspects the response for `Access-Control-Allow-Origin`. If the header is missing or does
not match, the response is discarded before `fetch()` ever sees it. The server already did the work; the
browser refuses to hand over the result.

A `POST` carrying `Content-Type: application/json` is **not** simple, so the browser preflights:

```
1. Browser  -> OPTIONS /api/matches
              Origin: http://localhost:5173
              Access-Control-Request-Method: POST
              Access-Control-Request-Headers: content-type

2. Server   -> 200 OK
              Access-Control-Allow-Origin: http://localhost:5173
              Access-Control-Allow-Methods: POST
              Access-Control-Allow-Headers: content-type

3. Browser  -> POST /api/matches   (only if step 2 covered what step 1 asked)
```

The result is cached for `Access-Control-Max-Age` seconds, so the `OPTIONS` appears once per session,
not before every request.

## In this project

```python
# backend/app/main.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,   # ["http://localhost:5173"]
    allow_credentials=True,
    allow_methods=["*"],                        # answers Access-Control-Request-Method
    allow_headers=["*"],                        # answers Access-Control-Request-Headers
)
```

`add_middleware` registers **middleware**: a layer wrapping every request and response. It runs before
route handlers and answers the `OPTIONS` preflight itself, which is why no `OPTIONS` handler appears
anywhere in `routers/matches.py`.

The allowed origin comes from configuration rather than a literal, because it differs per environment:

```
# backend/.env.example
CORS_ORIGINS=http://localhost:5173
```

The frontend triggers the preflight here, by sending JSON:

```javascript
// frontend/src/api/matches.js
headers: { 'Content-Type': 'application/json' },
```

Remove that header and the browser stops preflighting — and the server stops parsing the body.

## Gotchas

- **The error names the wrong culprit.** The console reports
  `Access to fetch at 'http://localhost:8000/api/matches' from origin 'http://localhost:5173' has been
  blocked by CORS policy`, while the backend logs a normal `200 OK` for the `OPTIONS`. Nothing is broken
  server-side.
- **A trailing slash breaks the match.** `"http://localhost:5173/"` is not the origin
  `http://localhost:5173`. Origins have no path component.
- **`allow_origins=["*"]` and `allow_credentials=True` are mutually exclusive** by specification. The
  browser rejects a wildcard when credentials are involved. Listing origins explicitly avoids the trap
  and is what production requires anyway.
- **Changing the Vite port breaks CORS.** Port is part of the origin; `CORS_ORIGINS` must follow.
- **CORS is not authorisation.** It stops *other websites' JavaScript* from reading your responses. It
  stops nothing else — anyone can still call the endpoint directly. Authentication is a separate concern.

## Related concepts

Same-origin policy; middleware as a general request-pipeline pattern (the same idea appears in Express
and Django); `SameSite` cookies; development proxies, which sidestep CORS by making the browser see a
single origin — a convenience that hides the mechanism, which is why this project does not use one yet.

## References

- [CORS — FastAPI](https://fastapi.tiangolo.com/tutorial/cors/) — `CORSMiddleware` parameters and defaults
- [Cross-Origin Resource Sharing — MDN](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS) — the mechanism header by header, from the browser's side
- [Fetch Standard — WHATWG](https://fetch.spec.whatwg.org/#http-cors-protocol) — the normative definition of the CORS protocol
