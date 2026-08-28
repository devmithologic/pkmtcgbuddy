"""Connection to MongoDB: a single client shared by the whole application."""

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from app.config import settings

# The client is created in connect_to_mongo() and stored here at module level.
# It starts as None because it doesn't exist yet when Python imports the file.
_client: AsyncMongoClient | None = None


async def connect_to_mongo() -> None:
    """Opens the client. Called once, when the process starts."""
    global _client
    _client = AsyncMongoClient(settings.mongodb_uri)
    # ping forces a real connection. Without this, AsyncMongoClient is lazy: it
    # doesn't touch the network until the first query, and a Mongo that is down
    # wouldn't be detected until a user made a request.
    await _client.admin.command("ping")


async def close_mongo_connection() -> None:
    """Closes the client and its sockets. Called when the process stops."""
    global _client
    if _client is not None:
        await _client.close()
        _client = None


def get_database() -> AsyncDatabase:
    """Returns the active database.

    Synchronous on purpose: it does no I/O, it just returns an object that
    points at the database. The I/O happens when a collection is queried.
    """
    if _client is None:
        raise RuntimeError("MongoDB no está conectado: ¿arrancó el lifespan de la app?")
    return _client[settings.db_name]


def to_object_id(value: str) -> ObjectId | None:
    """Converts a string into an ObjectId, or None if it isn't one.

    Lives here and not in a specific repository because it isn't a deck concern
    nor a session concern: it's a MongoDB concern, and every repository needs it.

    Exists because an invalid id arrives from the URL, i.e. from outside.
    Passing it straight to ObjectId() raises InvalidId, which if uncaught ends
    up as a 500 — when the correct response is a 404: the client asked for
    something that doesn't exist.
    """
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        return None
