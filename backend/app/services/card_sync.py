"""Descarga el catálogo de TCGdex y lo guarda en MongoDB.

Se ejecuta a mano, no en cada arranque:

    python -m app.services.card_sync            # cartas legales en Expanded
    python -m app.services.card_sync --format standard
    python -m app.services.card_sync --resort   # sin red: recalcula el orden

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
import re
import sys
import time

from pymongo import UpdateOne

from app.db import card_repository, set_repository
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


# Categorías cuya carta ES su nombre. Ver _reprint_key.
_CATEGORIAS_POR_NOMBRE = {"Trainer", "Energy"}

# El paréntesis con el que TCGdex distingue el personaje del arte:
# "Boss's Orders (Giovanni)". No está impreso en el nombre de la carta.
_SUFIJO_DE_ARTE = re.compile(r"\s*\([^)]*\)\s*$")


def _reprint_key(document: dict) -> str | None:
    """Qué cuenta como «la misma carta» al propagar legalidad.

    La clave depende de la CATEGORÍA, porque la regla del juego depende de la
    categoría:

    - **Pokémon: la huella completa** (`identity`, nombre más texto y ataques).
      Dos Pikachu de sets distintos atacan distinto: son cartas diferentes, no
      reimpresiones. Agruparlos por nombre fusionaría 1235 nombres de Pokémon
      que no tienen nada que ver entre sí.

    - **Trainer y Energy: el nombre.** Aquí el nombre ES la carta. No pueden
      existir dos Trainer distintos con el mismo nombre legales a la vez, y el
      reglamento dice que una impresión antigua se juega CON EL TEXTO ACTUAL.
      Por eso una diferencia de redacción no la convierte en otra carta.

    Esto último es un cambio de criterio, y conviene decir por qué. Antes todo se
    agrupaba por la huella, y el efecto colateral estaba anotado como límite
    conocido: Pokémon reescribió las plantillas de texto en la era Escarlata y
    Púrpura, así que Boss's Orders «Switch 1 of your opponent's Benched Pokémon
    with their Active Pokémon» no agrupa con «Switch in 1 of your opponent's
    Benched Pokémon to the Active Spot», siendo la misma carta. Son 25 nombres y
    192 impresiones.

    El motivo por el que se dejó abierto era que agrupar por nombre legalizaría
    por error la Poké Ball que lanza moneda. Eso ya no se sostiene: las tres
    impresiones de Poké Ball lanzan moneda, incluida la legal actual
    (`me03-080`, Mega Evolution). El bloqueo caducó cuando el juego reimprimió
    justo esa versión.

    Se quita el sufijo de arte porque «Boss's Orders (Giovanni)» es Boss's
    Orders: el paréntesis lo pone TCGdex, no la carta.
    """
    if document.get("category") in _CATEGORIAS_POR_NOMBRE:
        return "name:" + _SUFIJO_DE_ARTE.sub("", document["name"]).strip().lower()
    return document.get("identity")


def _apply_reprint_rule(documents: list[dict]) -> int:
    """Propaga la legalidad entre impresiones de la misma carta.

    El reglamento dice que si una carta se reimprime en un set legal, las
    impresiones antiguas también se pueden jugar. Boss's Orders tiene
    impresiones con marca D, F, G e I: todas son legales en Standard porque la
    de marca I lo es.

    TCGdex no modela eso. Marca la legalidad por impresión, así que reporta las
    de marca G como ilegales. Sin esta pasada, la aplicación rechazaría la
    Boss's Orders de Paldea Evolved que el jugador tiene en la mano.

    Qué se considera «la misma carta» lo decide `_reprint_key`, y no es lo mismo
    para un Pokémon que para un Trainer.

    Se hace aquí y no en el adaptador por una razón de forma: el adaptador
    traduce UNA carta y no puede saber nada de las demás. Esta regla necesita ver
    el conjunto entero, y el sync ya lo tiene en memoria antes de escribir.
    """
    legales_std: set[str] = set()
    legales_exp: set[str] = set()

    for doc in documents:
        clave = _reprint_key(doc)
        if clave:
            if doc["legal_standard"]:
                legales_std.add(clave)
            if doc["legal_expanded"]:
                legales_exp.add(clave)

    promovidas = 0
    for doc in documents:
        clave = _reprint_key(doc)
        if not clave:
            continue
        cambio = False
        if not doc["legal_standard"] and clave in legales_std:
            doc["legal_standard"] = True
            cambio = True
        if not doc["legal_expanded"] and clave in legales_exp:
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


def _stamp_set_dates(documents: list[dict], dates: dict[str, str]) -> int:
    """Copia en cada carta la fecha de su set. Devuelve cuántas quedaron sin ella.

    Es desnormalización deliberada, y el motivo es que ordenar por un campo que
    vive en OTRA colección obligaría a un $lookup en cada búsqueda. Con el dato
    en la propia carta, el índice compuesto de card_repository resuelve el orden
    sin tocar nada más.

    El precio de desnormalizar es el de siempre: si un set cambiara de fecha,
    estas copias quedarían viejas. Aquí no puede: la fecha de publicación de un
    set es pasado, y el pasado no se edita.
    """
    sin_fecha = 0
    for doc in documents:
        fecha = dates.get(card_repository.set_id_of(doc["_id"]))
        doc["set_release_date"] = fecha
        if not fecha:
            sin_fecha += 1
    return sin_fecha


async def resort() -> None:
    """Recalcula los campos de orden de las cartas YA guardadas. Sin red.

    Existe porque los 15021 documentos escritos antes de que existieran
    `sort_name`, `printing_rank` y `set_release_date` no los tienen, y sin ellos
    el buscador ordena por un campo que no está — que en Mongo no es un error,
    es simplemente todo empatado.

    Los tres se calculan con lo que ya hay en casa: los dos primeros salen del
    propio documento, y la fecha, de la colección `sets`. Resincronizar contra
    TCGdex también los arreglaría, pero serían minutos de red para calcular algo
    que no hace falta pedirle a nadie.
    """
    started = time.perf_counter()
    await connect_to_mongo()

    try:
        await card_repository.ensure_indexes()

        dates = await set_repository.release_dates()
        print(f"{len(dates)} sets con fecha")
        if not dates:
            print("La colección `sets` está vacía. Ejecuta antes:")
            print("  python -m app.services.set_sync")
            return

        escritas, sin_fecha = await card_repository.restamp_sort_fields(dates, BATCH_SIZE)

        # Y de paso se reaplica la regla de reimpresión, que también se puede
        # recalcular con lo que hay en casa. Solo añade legalidad, nunca la
        # quita, así que volver a pasarla es inofensivo.
        instantanea = await card_repository.legality_snapshot()
        antes = {d["_id"]: (d["legal_standard"], d["legal_expanded"]) for d in instantanea}
        promovidas = _apply_reprint_rule(instantanea)
        cambiadas = [
            d
            for d in instantanea
            if antes[d["_id"]] != (d["legal_standard"], d["legal_expanded"])
        ]
        await card_repository.save_legality(cambiadas, BATCH_SIZE)

        elapsed = time.perf_counter() - started
        print(
            f"Listo en {elapsed:.1f}s · {escritas} cartas · {sin_fecha} sin fecha de set"
            f" · {promovidas} impresiones promovidas a legal"
        )
    finally:
        await close_mongo_connection()


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

        # La fecha del set se estampa aquí y no en card_to_document porque no
        # sale de la carta: hay que ir a buscarla a otra colección, y esa es una
        # consulta que no puede colarse dentro de una función de traducción.
        sin_fecha = _stamp_set_dates(documents, await set_repository.release_dates())
        if sin_fecha:
            print(
                f"  {sin_fecha} cartas sin fecha de set. Si son muchas, falta:"
                " python -m app.services.set_sync"
            )

        # Después de estampar las fechas, no antes: elegir qué impresión de cada
        # energía se ofrece necesita saber cuál es la más reciente. Va aquí y no
        # en card_to_document porque es una decisión sobre el CONJUNTO, y esa
        # función ve una carta cada vez.
        duplicadas = card_repository.energy_duplicates(documents)
        for doc in documents:
            doc["is_energy_duplicate"] = doc["_id"] in duplicadas
        basicas = sum(1 for d in documents if d.get("is_basic_energy"))
        print(
            f"  energías básicas: {basicas} impresiones,"
            f" {basicas - len(duplicadas)} ofrecidas en el buscador"
        )

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
    parser.add_argument(
        "--resort",
        action="store_true",
        help=(
            "No descarga nada: recalcula los campos de orden de las cartas ya"
            " guardadas. Ejecutar después de set_sync la primera vez."
        ),
    )
    args = parser.parse_args()

    try:
        if args.resort:
            asyncio.run(resort())
        else:
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
