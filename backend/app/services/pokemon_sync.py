"""Downloads the national Pokédex and saves it into MongoDB.

    python -m app.services.pokemon_sync

Run by hand, and very rarely: the list only changes when a new generation
comes out. It's the same pattern as card_sync, just much smaller — one
request instead of 15,000 — so it needs neither bounded concurrency nor
batching.
"""

import asyncio
import sys
import time

from app.db import pokemon_repository
from app.db.mongo import close_mongo_connection, connect_to_mongo
from app.models.pokemon import PokemonRef
from app.services.pokemon_source import fetch_all


async def sync() -> None:
    started = time.perf_counter()
    await connect_to_mongo()

    try:
        await pokemon_repository.ensure_indexes()

        print("Descargando el Pokédex completo, con megas y formas…")
        # fetch_all returns plain dicts; the model is built here. This module
        # is the one that bridges the adapter and the model, so neither one
        # has to import the other — see fetch_all's docstring.
        pokemon = [PokemonRef(**entrada) for entrada in await fetch_all()]
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
