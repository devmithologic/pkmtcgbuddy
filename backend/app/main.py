"""Punto de entrada ASGI de la aplicación."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.mongo import close_mongo_connection, connect_to_mongo
from app.routers import cards, matches
from app.services.card_source import close_card_source, connect_card_source


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ciclo de vida de la aplicación.

    Lo que va antes del yield se ejecuta una vez al arrancar; lo que va después,
    una vez al parar. Entre medias, la app atiende peticiones.

    Aquí abrimos la conexión a Mongo. Es el sitio correcto porque queremos UN solo
    cliente para todo el proceso: abrir una conexión por petición es un error de
    rendimiento clásico —cada una implica handshake TCP y negociación con el
    servidor— y agota el pool de conexiones bajo carga.

    Sustituye a @app.on_event("startup"), obsoleto desde FastAPI 0.93. La ventaja
    de este formato: el arranque y el cierre de un mismo recurso quedan juntos en
    la misma función, así que es difícil olvidarse de cerrar lo que abriste.
    """
    await connect_to_mongo()
    await connect_card_source()
    yield
    # Se cierran en orden inverso a la apertura, la misma disciplina que una pila
    # de context managers anidados.
    await close_card_source()
    await close_mongo_connection()


app = FastAPI(
    title="pkmtcgbuddy API",
    lifespan=lifespan,
)

# CORS. El navegador aplica la política del mismo origen: JavaScript servido desde
# localhost:5173 no puede leer respuestas de localhost:8000, porque el puerto los
# hace orígenes distintos. Este middleware es cómo el servidor da permiso.
#
# Ojo con el sentido: lo aplica el NAVEGADOR, no el servidor. Por eso curl funciona
# aunque esto falte, y por eso el error aparece solo en la consola del navegador.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Todas las rutas del router quedan bajo /api: /api/matches.
app.include_router(matches.router, prefix="/api")
app.include_router(cards.router, prefix="/api")


@app.get("/api/health")
async def health() -> dict[str, str]:
    """Comprobación de que la app está viva. Útil para verificar que el servidor
    arrancó antes de sospechar de la base de datos o del frontend."""
    return {"status": "ok"}
