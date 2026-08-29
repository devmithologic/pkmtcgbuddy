"""Downloads TCGdex's catalogue and saves it into MongoDB.

Run by hand, not on every startup:

    python -m app.services.card_sync            # cards legal in Expanded
    python -m app.services.card_sync --format standard
    python -m app.services.card_sync --resort   # no network: recomputes order

Why it exists: a live call per search turns a third party's response time into
our own. On August 9, 2026, TCGdex's API was down — TLS handshake timing out,
then connection refused — and search stopped working entirely even though our
own server and our own database were perfectly fine.

By syncing, TCGdex goes from being a runtime dependency to a deploy-time one.
It can go down: search keeps working.

About the N+1 in here: TCGdex's list doesn't return category, rarity, or
legality, so one request per card is needed. That is exactly what
log_mentor/08_HTTP_N_PLUS_ONE.md says to avoid... inside a web request. In a
batch job the math is different: nobody is waiting in front of a screen, it
runs once every few weeks, and the cost is paid here so that every search
doesn't have to pay it. The same structure is a flaw or a decision depending on
who is the one waiting.
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

# How many details are requested at once. Neither 1 (painfully slow) nor 200
# (rude, and a good way to get rate-limited). TCGdex doesn't publish a rate
# limit, so this number is prudence, not a requirement.
CONCURRENCY = 8

# How many cards get written to Mongo at a time. Writing one at a time is
# thousands of network round trips; buffering everything in memory and writing
# at the end means losing it all if something fails partway through.
BATCH_SIZE = 200


async def _list_all_ids(deck_format: DeckFormat) -> list[str]:
    """Walks the paginated list until it runs out."""
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
    """Requests each card's detail with bounded concurrency.

    The Semaphore is what turns "fire off 6,000 requests" into "keep at most
    8 in flight". Without it, asyncio would fire them all at once: it would
    exhaust the connection pool and would probably get us rate-limited.
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
                # A card that fails must not abort the whole sync. It's
                # logged and we move on: 5,999 cards beats zero.
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


# Categories whose card IS its name. See _reprint_key.
_CATEGORIES_BY_NAME = {"Trainer", "Energy"}

# The parenthetical TCGdex uses to distinguish the character from the artwork:
# "Boss's Orders (Giovanni)". It isn't printed on the card's name.
_ART_SUFFIX = re.compile(r"\s*\([^)]*\)\s*$")


def _reprint_key(document: dict) -> str | None:
    """What counts as "the same card" when propagating legality.

    The key depends on the CATEGORY, because the game's rule depends on the
    category:

    - **Pokémon: the full fingerprint** (`identity`, name plus text and
      attacks). Two Pikachu from different sets attack differently: they are
      different cards, not reprints of each other. Grouping them by name
      would merge 1235 Pokémon names that have nothing to do with each other.

    - **Trainer and Energy: the name.** Here the name IS the card. Two
      different Trainers with the same name can't both be legal at the same
      time, and the rulebook says an old printing is played WITH THE CURRENT
      TEXT. So a wording difference doesn't make it a different card.

    This last part is a change of approach, and it's worth saying why.
    Everything used to be grouped by fingerprint, and the side effect was
    noted as a known limitation: Pokémon rewrote its text templates in the
    Scarlet & Violet era, so Boss's Orders' "Switch 1 of your opponent's
    Benched Pokémon with their Active Pokémon" didn't group with "Switch in 1
    of your opponent's Benched Pokémon to the Active Spot", even though it's
    the same card. That's 25 names and 192 printings.

    The reason it was left open was that grouping by name would wrongly make
    the coin-flipping Poké Ball legal. That no longer holds: all three
    printings of Poké Ball flip a coin, including the currently legal one
    (`me03-080`, Mega Evolution). The concern expired the moment the game
    reprinted that very version.

    The art suffix is stripped because "Boss's Orders (Giovanni)" is Boss's
    Orders: the parenthetical is TCGdex's doing, not the card's.
    """
    if document.get("category") in _CATEGORIES_BY_NAME:
        return "name:" + _ART_SUFFIX.sub("", document["name"]).strip().lower()
    return document.get("identity")


def _apply_reprint_rule(documents: list[dict]) -> int:
    """Propagates legality across printings of the same card.

    The rulebook says that if a card is reprinted in a legal set, older
    printings become playable too. Boss's Orders has printings with
    regulation marks D, F, G, and I: all of them are legal in Standard
    because the I-marked one is.

    TCGdex doesn't model that. It marks legality per printing, so it reports
    the G-marked ones as illegal. Without this pass, the application would
    reject the Paldea Evolved Boss's Orders the player is holding.

    What counts as "the same card" is decided by `_reprint_key`, and it isn't
    the same for a Pokémon as it is for a Trainer.

    This is done here and not in the adapter, for a reason of shape: the
    adapter translates ONE card and can't know anything about the others.
    This rule needs to see the whole set, and the sync already has it in
    memory before writing.
    """
    legal_standard_keys: set[str] = set()
    legal_expanded_keys: set[str] = set()

    for doc in documents:
        key = _reprint_key(doc)
        if key:
            if doc["legal_standard"]:
                legal_standard_keys.add(key)
            if doc["legal_expanded"]:
                legal_expanded_keys.add(key)

    promoted = 0
    for doc in documents:
        key = _reprint_key(doc)
        if not key:
            continue
        changed = False
        if not doc["legal_standard"] and key in legal_standard_keys:
            doc["legal_standard"] = True
            changed = True
        if not doc["legal_expanded"] and key in legal_expanded_keys:
            doc["legal_expanded"] = True
            changed = True
        promoted += changed

    return promoted


async def _write(documents: list[dict]) -> tuple[int, int]:
    """Writes in batches with upsert, so re-syncing is safe.

    UpdateOne(..., upsert=True) inserts if it doesn't exist and updates if it
    does. The alternative — dropping everything and reinserting — leaves the
    collection empty for a few seconds: any search in that gap finds nothing.

    bulk_write sends every operation in the batch in a single network round
    trip.
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
            ordered=False,  # a failure doesn't stop the rest of the batch
        )
        inserted += result.upserted_count
        updated += result.modified_count
        print(f"  escritas {min(start + BATCH_SIZE, len(documents))}/{len(documents)}…",
              end="\r", flush=True)

    print()
    return inserted, updated


def _stamp_set_dates(documents: list[dict], dates: dict[str, str]) -> int:
    """Copies its set's date onto each card. Returns how many were left without one.

    This is deliberate denormalization, and the reason is that sorting by a
    field that lives in ANOTHER collection would force a $lookup on every
    search. With the value on the card itself, card_repository's compound
    index resolves the ordering without touching anything else.

    The cost of denormalizing is the usual one: if a set's date ever changed,
    these copies would go stale. It can't happen here: a set's release date is
    the past, and the past doesn't get edited.
    """
    without_date = 0
    for doc in documents:
        date = dates.get(card_repository.set_id_of(doc["_id"]))
        doc["set_release_date"] = date
        if not date:
            without_date += 1
    return without_date


async def resort() -> None:
    """Recomputes the sort fields of cards ALREADY saved. No network.

    It exists because the 15021 documents written before `sort_name`,
    `printing_rank`, and `set_release_date` existed don't have them, and
    without them search sorts by a field that isn't there — which in Mongo
    isn't an error, it's just everything tied.

    All three are computed from what's already on hand: the first two come
    from the document itself, and the date from the `sets` collection.
    Re-syncing against TCGdex would also fix them, but that would be minutes
    of network calls to compute something nobody needs to be asked for.
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

        written, without_date = await card_repository.restamp_sort_fields(dates, BATCH_SIZE)

        # And while we're at it, the reprint rule is reapplied too, since it
        # can also be recomputed from what's already on hand. It only ever
        # adds legality, never removes it, so running it again is harmless.
        snapshot = await card_repository.legality_snapshot()
        before = {d["_id"]: (d["legal_standard"], d["legal_expanded"]) for d in snapshot}
        promoted = _apply_reprint_rule(snapshot)
        changed_docs = [
            d
            for d in snapshot
            if before[d["_id"]] != (d["legal_standard"], d["legal_expanded"])
        ]
        await card_repository.save_legality(changed_docs, BATCH_SIZE)

        elapsed = time.perf_counter() - started
        print(
            f"Listo en {elapsed:.1f}s · {written} cartas · {without_date} sin fecha de set"
            f" · {promoted} impresiones promovidas a legal"
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

        promoted = _apply_reprint_rule(documents)
        print(f"  regla de reimpresión: {promoted} impresiones promovidas a legal")

        # The set's date is stamped here and not in card_to_document because
        # it doesn't come from the card: it has to be looked up in another
        # collection, and that's a query that shouldn't sneak into a
        # translation function.
        without_date = _stamp_set_dates(documents, await set_repository.release_dates())
        if without_date:
            print(
                f"  {without_date} cartas sin fecha de set. Si son muchas, falta:"
                " python -m app.services.set_sync"
            )

        # After stamping the dates, not before: deciding which printing of
        # each energy gets offered needs to know which one is the most
        # recent. It goes here and not in card_to_document because it's a
        # decision about the WHOLE SET, and that function only ever sees one
        # card at a time.
        duplicates = card_repository.energy_duplicates(documents)
        for doc in documents:
            doc["is_energy_duplicate"] = doc["_id"] in duplicates
        basic_count = sum(1 for d in documents if d.get("is_basic_energy"))
        print(
            f"  energías básicas: {basic_count} impresiones,"
            f" {basic_count - len(duplicates)} ofrecidas en el buscador"
        )

        inserted, updated = await _write(documents)

        total = await card_repository.count_cards()
        elapsed = time.perf_counter() - started
        print(
            f"\nListo en {elapsed:.0f}s · {inserted} nuevas · {updated} actualizadas"
            f" · {total} cartas en la base"
        )
    finally:
        # finally, not at the end of the try: if TCGdex fails partway
        # through, the connections still get closed.
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
