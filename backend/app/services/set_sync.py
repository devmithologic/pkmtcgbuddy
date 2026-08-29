"""Downloads the sets with their official abbreviation and their date, and saves them into Mongo.

    python -m app.services.set_sync

A job kept separate from the card one, rather than folded into it, because of
timing: this one takes seconds — 218 requests — and the card one takes
minutes. Keeping them apart lets abbreviations be refreshed when a new set
comes out without re-downloading 15,000 cards.

Run by hand. It's needed for two things: importing and exporting decklists —
see `services/deck_text.py` — and sorting a card's printings from newest to
oldest, which is what makes searching for a basic energy find the plain one
and not the gold secret rare.
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

        print("Descargando los sets, sus abreviaturas oficiales y sus fechas…")
        sets = await fetch_sets()
        with_abbreviation = sum(1 for s in sets if s["abbreviation"])
        with_date = sum(1 for s in sets if s["release_date"])
        print(f"  {len(sets)} sets · {with_abbreviation} con abreviatura · {with_date} con fecha")

        written = await set_repository.replace_all(sets)
        total = await set_repository.count()

        print(
            f"Listo en {time.perf_counter() - started:.1f}s · "
            f"{written} escritos · {total} en la base"
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
