"""Descarga los sets con su abreviatura oficial y los guarda en MongoDB.

    python -m app.services.set_sync

Job aparte del de cartas, y no dentro de él, por el tiempo: este tarda segundos
—218 peticiones— y el de cartas, minutos. Tenerlos separados permite refrescar
las abreviaturas cuando sale un set nuevo sin volver a bajar 15.000 cartas.

Se ejecuta a mano. Hace falta para importar y exportar listas de mazo; ver
`services/deck_text.py`.
"""

import asyncio
import sys
import time

from app.db import set_repository
from app.db.mongo import close_mongo_connection, connect_to_mongo
from app.services.card_source import close_card_source, connect_card_source, fetch_sets


async def sync() -> None:
    started = time.perf_counter()
    await connect_to_mongo()
    await connect_card_source()

    try:
        await set_repository.ensure_indexes()

        print("Descargando los sets y sus abreviaturas oficiales…")
        sets = await fetch_sets()
        print(f"  {len(sets)} sets con abreviatura")

        escritos = await set_repository.replace_all(sets)
        total = await set_repository.count()

        print(
            f"Listo en {time.perf_counter() - started:.1f}s · "
            f"{escritos} escritos · {total} en la base"
        )
    finally:
        await close_card_source()
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
