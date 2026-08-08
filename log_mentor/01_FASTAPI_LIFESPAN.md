# Application Lifespan

> **Stack:** FASTAPI · **Introduced in:** first vertical slice — connecting the API to MongoDB · **Date:** 2026-08-08

## Definition

The **lifespan** is an async context manager that runs code once when an ASGI application starts and
once when it shuts down, wrapping the entire period during which the app serves requests.

## Why it exists

Some resources should exist once per process, not once per request: database clients, connection
pools, ML models, message-queue consumers.

Without a lifespan, the tempting shortcut is to open the resource inside the request handler:

```python
@app.get("/matches")
async def list_matches():
    client = AsyncMongoClient(uri)   # wrong
    ...
```

Every request now pays for a TCP handshake and a server-capability negotiation, and nothing ever
closes the client. Under load the process runs out of sockets. The database sees hundreds of
short-lived connections instead of a pool it can reuse.

The opposite shortcut — opening the client at import time, at module level — appears to work but
breaks in a subtler way: the client binds to whatever event loop exists at import, which is not
necessarily the loop the server ends up running. The symptom is a hang or a
`RuntimeError: attached to a different loop` under a test runner or a multi-worker deployment.

## How it works

The lifespan is part of the **ASGI** specification, the Python interface between a web server
(uvicorn) and a framework (FastAPI). Before accepting any connection, the server sends the
application a `lifespan.startup` message; when stopping, `lifespan.shutdown`.

FastAPI exposes this as a single function split by `yield`:

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    resource = await open_resource()   # runs once, before the first request
    yield                              # app serves requests here
    await resource.close()             # runs once, after the last request

app = FastAPI(lifespan=lifespan)
```

The sequence is strict: nothing is served before the code above `yield` finishes, and shutdown code
only runs after in-flight requests drain.

This supersedes `@app.on_event("startup")` and `@app.on_event("shutdown")`, deprecated since FastAPI
0.93. The advantage of the newer form is structural: setup and teardown of the same resource sit in
one function, so it is hard to write the first and forget the second. That is the same reasoning
behind `with open(...)` instead of a manual `close()`.

## In this project

```python
# backend/app/main.py
@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_to_mongo()
    yield
    await close_mongo_connection()

app = FastAPI(title="pkmtcgbuddy API", lifespan=lifespan)
```

The actual client lives in its own module, so route handlers never touch construction details:

```python
# backend/app/db/mongo.py
_client: AsyncMongoClient | None = None

async def connect_to_mongo() -> None:
    global _client
    _client = AsyncMongoClient(settings.mongodb_uri)
    await _client.admin.command("ping")   # force a real connection

def get_database() -> AsyncDatabase:
    if _client is None:
        raise RuntimeError("MongoDB is not connected: did the app lifespan run?")
    return _client[settings.db_name]
```

The `ping` is deliberate. `AsyncMongoClient` is **lazy**: constructing it touches no network, so a
database that is down would not be noticed until the first user request. Pinging during startup turns
a silent misconfiguration into a loud failure before the app accepts traffic — a **fail-fast** check.

`get_database()` is synchronous on purpose. It performs no I/O; it returns a handle. The I/O happens
when a collection is actually queried.

## Gotchas

- **Forgetting `lifespan=lifespan`.** Defining the function is not enough — it must be passed to the
  `FastAPI()` constructor. Symptom: `RuntimeError: MongoDB is not connected` on the first request,
  with a startup log that looks completely normal.
- **`--reload` runs the lifespan again on every code change.** That is correct behaviour, but it means
  startup work is repeated constantly in development. Keep it cheap.
- **Exceptions before `yield` abort startup.** The server exits instead of serving broken requests.
  This is desirable; do not wrap the whole lifespan in a bare `try/except`.
- **Module-level global state does not survive multiple worker processes.** Each uvicorn worker is a
  separate process with its own `_client`. Fine here; worth remembering before storing anything
  stateful, like a cache, this way.

## Related concepts

Dependency injection with `Depends()` (the per-request counterpart to this per-process setup);
connection pooling; graceful shutdown; `see 03_MONGODB_BSON_SERIALIZATION.md` for what happens to the
data once the connection is open.

## References

- [Lifespan Events — FastAPI](https://fastapi.tiangolo.com/advanced/events/) — official documentation for the `lifespan` context manager
- [ASGI Lifespan Protocol](https://asgi.readthedocs.io/en/latest/specs/lifespan.html) — the specification the server implements underneath
