"""Descarga el catálogo de TCGdex y lo guarda en MongoDB.

Se ejecuta a mano, no en cada arranque:

    python -m app.services.card_sync            # cartas legales en Expanded
    python -m app.services.card_sync --format standard

Por qué existe: una llamada en vivo por búsqueda convierte el tiempo de servicio
de un tercero en el nuestro. El 9 de agosto de 2026 la API de TCGdex estuvo caída
—handshake TLS agotado, luego conexión rechazada— y el buscador dejó de funcionar
por completo aunque nuestro servidor y nuestra base estaban perfectos.

Sincronizando, TCGdex pasa de ser una dependencia de tiempo de ejecución a una de
tiempo de despliegue. Puede caerse: el buscador sigue.

Sobre el N+1 que hay aquí dentro: el listado de TCGdex no devuelve categoría,
rareza ni legalidad, así que hace falta una petición por carta. Eso es exactamente
lo que log_mentor/08_HTTP_N_PLUS_ONE.md dice que hay que evitar... en una petición
web. En un trabajo por lotes el cálculo es otro: nadie espera delante de una
pantalla, se ejecuta una vez cada varias semanas, y el coste se paga aquí para que
no lo pague cada búsqueda. La misma estructura es un defecto o una decisión según
quién esté esperando.
"""

import argparse
import asyncio
import sys
import time

from pymongo import UpdateOne

from app.db import card_repository
from app.db.mongo import close_mongo_connection, connect_to_mongo
from app.models.card import DeckFormat
from app.services import card_source
from app.services.card_source import (
    CardSourceError,
    close_card_source,
    connect_card_source,
)

# Cuántos detalles se piden a la vez. Ni 1 (lentísimo) ni 200 (maleducado, y buena
# forma de que te limiten). TCGdex no publica límite de peticiones, así que este
# número es prudencia, no obligación.
CONCURRENCY = 8

# Cada cuántas cartas se escribe en Mongo. Escribir de una en una son miles de
# viajes de red; acumular todo en memoria y escribir al final significa perderlo
# todo si algo falla a mitad.
BATCH_SIZE = 200


async def _list_all_ids(deck_format: DeckFormat) -> list[str]:
    """Recorre el listado paginado hasta agotarlo."""
    ids: list[str] = []
    page = 1

    while True:
        result = await card_source.search_cards(
            deck_format=deck_format, page=page, page_size=100
        )
        ids.extend(card.id for card in result.cards)
        print(f"  listadas {len(ids)} cartas…", end="\r", flush=True)

        if not result.has_more:
            break
        page += 1

    print()
    return ids


async def _fetch_details(ids: list[str]) -> list[dict]:
    """Pide el detalle de cada carta con concurrencia acotada.

    El Semaphore es lo que convierte "lanza 6.000 peticiones" en "ten como mucho
    8 en vuelo". Sin él, asyncio las dispararía todas a la vez: agotaría el pool
    de conexiones y probablemente provocaría que nos bloqueen.
    """
    semaphore = asyncio.Semaphore(CONCURRENCY)
    documents: list[dict] = []
    failed: list[str] = []
    done = 0

    async def fetch(card_id: str) -> None:
        nonlocal done
        async with semaphore:
            try:
                card = await card_source.get_card(card_id)
                if card is not None:
                    documents.append(card_repository.card_to_document(card))
            except (CardSourceError, Exception) as exc:  # noqa: B014
                # Una carta que falla no debe abortar la sincronización entera.
                # Se anota y se sigue: 5.999 cartas son mejor que ninguna.
                failed.append(f"{card_id}: {type(exc).__name__}")
            finally:
                done += 1
                if done % 25 == 0:
                    print(f"  detalles {done}/{len(ids)}…", end="\r", flush=True)

    await asyncio.gather(*(fetch(card_id) for card_id in ids))
    print(f"  detalles {done}/{len(ids)}   ")

    if failed:
        print(f"  {len(failed)} cartas fallaron; primeras: {failed[:3]}")

    return documents


def _apply_reprint_rule(documents: list[dict]) -> int:
    """Propaga la legalidad entre impresiones de la misma carta.

    El reglamento dice que si una carta se reimprime en un set legal, las
    impresiones antiguas del mismo texto también se pueden jugar. Boss's Orders
    tiene impresiones con marca D, F, G e I: las seis son legales en Standard
    porque la de marca I lo es.

    TCGdex no modela eso. Marca la legalidad por impresión, así que reporta las
    de marca G como ilegales. Sin esta pasada, la aplicación rechazaría la
    Boss's Orders de Paldea Evolved que el jugador tiene en la mano.

    El agrupamiento es por `identity` —nombre más texto— y no por nombre, porque
    dos Pokémon llamados "Pikachu" de sets distintos tienen ataques distintos:
    son cartas diferentes, no reimpresiones.

    Se hace aquí y no en el adaptador por una razón de forma: el adaptador
    traduce UNA carta y no puede saber nada de las demás. Esta regla necesita ver
    el conjunto entero, y el sync ya lo tiene en memoria antes de escribir.
    """
    legales_std: set[str] = set()
    legales_exp: set[str] = set()

    for doc in documents:
        if doc.get("identity"):
            if doc["legal_standard"]:
                legales_std.add(doc["identity"])
            if doc["legal_expanded"]:
                legales_exp.add(doc["identity"])

    promovidas = 0
    for doc in documents:
        ident = doc.get("identity")
        if not ident:
            continue
        cambio = False
        if not doc["legal_standard"] and ident in legales_std:
            doc["legal_standard"] = True
            cambio = True
        if not doc["legal_expanded"] and ident in legales_exp:
            doc["legal_expanded"] = True
            cambio = True
        promovidas += cambio

    return promovidas


async def _write(documents: list[dict]) -> tuple[int, int]:
    """Escribe en lotes con upsert, para que resincronizar sea seguro.

    UpdateOne(..., upsert=True) inserta si no existe y actualiza si existe. La
    alternativa —borrar todo y reinsertar— deja la colección vacía durante unos
    segundos: cualquier búsqueda en ese hueco no encuentra nada.

    bulk_write manda todas las operaciones del lote en un solo viaje de red.
    """
    collection = card_repository._collection()
    inserted = updated = 0

    for start in range(0, len(documents), BATCH_SIZE):
        batch = documents[start : start + BATCH_SIZE]
        result = await collection.bulk_write(
            [
                UpdateOne({"_id": doc["_id"]}, {"$set": doc}, upsert=True)
                for doc in batch
            ],
            ordered=False,  # un fallo no detiene el resto del lote
        )
        inserted += result.upserted_count
        updated += result.modified_count
        print(f"  escritas {min(start + BATCH_SIZE, len(documents))}/{len(documents)}…",
              end="\r", flush=True)

    print()
    return inserted, updated


async def sync(deck_format: DeckFormat) -> None:
    started = time.perf_counter()

    await connect_to_mongo()
    await connect_card_source()

    try:
        await card_repository.ensure_indexes()

        print(f"Sincronizando cartas legales en {deck_format.value}…")
        ids = await _list_all_ids(deck_format)

        if not ids:
            print("TCGdex no devolvió cartas. ¿Está disponible?")
            return

        documents = await _fetch_details(ids)

        promovidas = _apply_reprint_rule(documents)
        print(f"  regla de reimpresión: {promovidas} impresiones promovidas a legal")

        inserted, updated = await _write(documents)

        total = await card_repository.count_cards()
        elapsed = time.perf_counter() - started
        print(
            f"\nListo en {elapsed:.0f}s · {inserted} nuevas · {updated} actualizadas"
            f" · {total} cartas en la base"
        )
    finally:
        # finally, no al final del try: si TCGdex falla a mitad, las conexiones
        # se cierran igual.
        await close_card_source()
        await close_mongo_connection()


def main() -> int:
    parser = argparse.ArgumentParser(description="Sincroniza cartas de TCGdex a MongoDB")
    parser.add_argument(
        "--format",
        choices=[f.value for f in DeckFormat],
        default=DeckFormat.EXPANDED.value,
        help=(
            "Formato a sincronizar. Expanded por defecto porque incluye a Standard:"
            " sincronizar Standard dejaría fuera cartas que un mazo Expanded necesita."
        ),
    )
    args = parser.parse_args()

    try:
        asyncio.run(sync(DeckFormat(args.format)))
    except KeyboardInterrupt:
        print("\nInterrumpido. Lo ya escrito se conserva; volver a ejecutar continúa.")
        return 130
    except Exception as exc:
        print(f"\nFalló la sincronización: {type(exc).__name__}: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
