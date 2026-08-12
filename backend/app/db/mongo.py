"""Conexión a MongoDB: un único cliente compartido por toda la aplicación."""

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from app.config import settings

# El cliente se crea en connect_to_mongo() y se guarda aquí a nivel de módulo.
# Empieza en None porque todavía no existe cuando Python importa el fichero.
_client: AsyncMongoClient | None = None


async def connect_to_mongo() -> None:
    """Abre el cliente. Se llama una vez, al arrancar el proceso."""
    global _client
    _client = AsyncMongoClient(settings.mongodb_uri)
    # ping fuerza una conexión real. Sin esto, AsyncMongoClient es perezoso: no
    # toca la red hasta la primera consulta, y un Mongo apagado no se detectaría
    # hasta que un usuario hiciera una petición.
    await _client.admin.command("ping")


async def close_mongo_connection() -> None:
    """Cierra el cliente y sus sockets. Se llama al parar el proceso."""
    global _client
    if _client is not None:
        await _client.close()
        _client = None


def get_database() -> AsyncDatabase:
    """Devuelve la base de datos activa.

    Es síncrona a propósito: no hace E/S, solo devuelve un objeto que apunta a la
    base. La E/S ocurre cuando se consulta una colección.
    """
    if _client is None:
        raise RuntimeError("MongoDB no está conectado: ¿arrancó el lifespan de la app?")
    return _client[settings.db_name]


def to_object_id(value: str) -> ObjectId | None:
    """Convierte una cadena en ObjectId, o None si no lo es.

    Vive aquí y no en un repositorio concreto porque no es cosa de mazos ni de
    sesiones: es una preocupación de MongoDB, y la necesitan todos.

    Existe porque un id inválido llega desde la URL, es decir, desde fuera.
    Pasarlo directo a ObjectId() lanza InvalidId, que sin capturar acaba en un
    500 — cuando lo correcto es un 404: el cliente pidió algo que no existe.
    """
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        return None
