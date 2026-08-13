"""Descarga el Pokédex nacional y lo guarda en MongoDB.

    python -m app.services.pokemon_sync

Se ejecuta a mano y muy de vez en cuando: la lista solo cambia cuando sale una
generación nueva. Es el mismo patrón que card_sync, pero mucho más pequeño —una
petición en vez de 15.000— así que no necesita concurrencia acotada ni lotes.
"""

import asyncio
import sys
import time

from app.db import pokemon_repository
from app.db.mongo import close_mongo_connection, connect_to_mongo
from app.services.pokemon_source import fetch_national_dex


async def sync() -> None:
    started = time.perf_counter()
    await connect_to_mongo()

    try:
        await pokemon_repository.ensure_indexes()

        print("Descargando el Pokédex nacional…")
        pokemon = await fetch_national_dex()
        print(f"  {len(pokemon)} Pokémon")

        escritos = await pokemon_repository.replace_all(pokemon)
        total = await pokemon_repository.count()

        print(
            f"Listo en {time.perf_counter() - started:.1f}s · "
            f"{escritos} escritos · {total} en la base"
        )
    finally:
        await close_mongo_connection()


def main() -> int:
    try:
        asyncio.run(sync())
    except Exception as exc:
        print(f"Falló la sincronización: {type(exc).__name__}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
