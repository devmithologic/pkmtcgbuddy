"""ASGI entry point for the application."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import (
    card_repository,
    deck_repository,
    folder_repository,
    set_repository,
    pokemon_repository,
    session_repository,
)
from app.db.mongo import close_mongo_connection, connect_to_mongo
from app.routers import cards, decks, folders, pokemon, sessions


@asynccontextmanager
async def lifespan(app: FastAPI):
    """The application's lifecycle.

    What goes before the yield runs once at startup; what goes after, once at
    shutdown. In between, the app serves requests.

    This is where the Mongo connection is opened. It's the right place because
    we want ONE single client for the whole process: opening one connection per
    request is a classic performance mistake —each one means a TCP handshake and
    negotiation with the server— and it exhausts the connection pool under load.

    Supersedes @app.on_event("startup"), deprecated since FastAPI 0.93. The
    advantage of this format: the startup and the shutdown of the same resource
    sit together in the same function, so it's hard to forget to close what you
    opened.
    """
    await connect_to_mongo()

    # Idempotent: if the indexes already exist, it does nothing. Creating them
    # here keeps a fresh deployment from starting out doing collection scans
    # without anyone noticing.
    await card_repository.ensure_indexes()
    await deck_repository.ensure_indexes()
    await session_repository.ensure_indexes()
    await pokemon_repository.ensure_indexes()
    await folder_repository.ensure_indexes()
    await set_repository.ensure_indexes()

    yield

    await close_mongo_connection()

    # The web process no longer opens an HTTP client toward TCGdex: nothing
    # external gets consulted while handling a request. That client now lives
    # in the sync job, which opens and closes it on its own.


app = FastAPI(
    title="pkmtcgbuddy API",
    lifespan=lifespan,
)

# CORS. The browser enforces the same-origin policy: JavaScript served from
# localhost:5173 cannot read responses from localhost:8000, because the port
# makes them different origins. This middleware is how the server grants
# permission.
#
# Watch the direction: it's enforced by the BROWSER, not the server. That's why
# curl works even without this, and why the error shows up only in the
# browser's console.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# All routes live under /api: /api/sessions, /api/decks, /api/cards.
app.include_router(sessions.router, prefix="/api")
app.include_router(cards.router, prefix="/api")
app.include_router(decks.router, prefix="/api")
app.include_router(pokemon.router, prefix="/api")
app.include_router(folders.router, prefix="/api")


@app.get("/api/health")
async def health() -> dict[str, str]:
    """Check that the app is alive. Useful for confirming the server started
    before suspecting the database or the frontend."""
    return {"status": "ok"}
