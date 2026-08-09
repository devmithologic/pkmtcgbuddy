# Batch Jobs: Bounded Concurrency, Bulk Writes, Idempotency

> **Stack:** PYTHON · **Introduced in:** syncing the card catalogue into MongoDB · **Date:** 2026-08-09

## Definition

A **batch job** processes a bounded set of work in one run, outside the request/response cycle.
Nobody is waiting on a screen, so the constraints invert: total throughput and restartability matter,
per-item latency does not.

## Why it exists

Some work does not belong in a web request. Downloading 3,318 cards takes over a minute — no HTTP
client will wait, and no user should. Moving it to a job that runs on its own schedule turns an
impossible request into a routine one.

The inversion of constraints is the interesting part, because it makes previously-bad patterns
acceptable:

| | Web request | Batch job |
| --- | --- | --- |
| Who waits | a person | nobody |
| Acceptable duration | milliseconds | minutes |
| N+1 access | a defect | often unavoidable, and fine |
| Partial failure | fail the request | log it, keep going |
| Re-running it | not a thing | must be safe |

`card_sync.py` contains an N+1 — one detail request per card — which
`08_HTTP_N_PLUS_ONE.md` calls a defect. Both are right. The same structure is a bug or a decision
depending on who is waiting.

## How it works

Three mechanisms carry most batch jobs.

**Bounded concurrency.** Firing 3,318 requests at once exhausts the connection pool and gets you rate
limited. A semaphore caps how many run simultaneously:

```python
semaphore = asyncio.Semaphore(8)

async def fetch(item_id):
    async with semaphore:          # at most 8 inside this block at a time
        return await get(item_id)

await asyncio.gather(*(fetch(i) for i in ids))
```

`gather` schedules everything immediately; the semaphore is what makes only eight of them *run*.
Without it, `gather` over thousands of coroutines is a self-inflicted denial of service.

**Bulk writes.** One database round trip per row is thousands of round trips. Batching amortises
them:

```python
await collection.bulk_write(
    [UpdateOne({"_id": d["_id"]}, {"$set": d}, upsert=True) for d in batch],
    ordered=False,     # one failure does not stop the rest
)
```

**Idempotency.** A job that cannot be safely re-run is a job you are afraid of. `upsert=True` inserts
when absent and updates when present, so running the sync twice is harmless. The alternative —
delete everything, then reinsert — leaves the collection empty for several seconds, and any search in
that window returns nothing.

## In this project

```python
# backend/app/services/card_sync.py
CONCURRENCY = 8      # polite, not mandated: TCGdex publishes no rate limit
BATCH_SIZE = 200     # writing one at a time is thousands of round trips;
                     # accumulating everything loses it all on a mid-run failure
```

Partial failure is tolerated on purpose:

```python
try:
    card = await card_source.get_card(card_id)
    ...
except Exception as exc:
    failed.append(f"{card_id}: {type(exc).__name__}")   # note it, keep going
```

One card that fails must not abort the run. 5,999 cards are better than none, and the failures are
reported at the end so they are not silent.

Cleanup uses `finally`, so an upstream failure mid-run still closes both connections:

```python
finally:
    await close_card_source()
    await close_mongo_connection()
```

Measured on the real run: **3,318 cards in 69 seconds, zero failures.** Sequentially that would have
been roughly 3,318 × 150 ms ≈ 8 minutes; concurrency of 8 brought it to about one.

The job is invoked by hand, not on startup:

```bash
python -m app.services.card_sync --format expanded
```

Running it at startup would make every deploy wait a minute and hammer TCGdex on every restart —
including the `--reload` restarts that happen whenever a file is saved.

## Gotchas

- **`asyncio.gather` without a semaphore is a load test against someone else's server.** The
  coroutines are created eagerly; only the semaphore limits how many run.
- **`bulk_write(ordered=True)`, the default, stops at the first error.** For independent rows,
  `ordered=False` is what you want.
- **Progress output needs `flush=True`.** stdout is block-buffered when not a terminal, so a job that
  prints progress can look frozen while working fine.
- **Delete-then-insert is not idempotent in any useful sense.** It has a window where the data does
  not exist. Upsert has none.
- **`except Exception` is right here and wrong in a request handler.** Here it means "one bad row must
  not kill the run"; there it means "swallow bugs".
- **Cached data goes stale, and that is the price.** Standard was 3,318 cards at sync time and 3,345
  the next day — 27 new cards invisible until the next run. Deciding how often to re-sync is now a
  real decision the live proxy never forced.

## Related concepts

`see 08_HTTP_N_PLUS_ONE.md` — the same structure judged by a different standard;
`see 14_HTTP_RUNTIME_VS_DEPLOY_DEPENDENCY.md` — why this job exists at all; cron and scheduled jobs;
backpressure; at-least-once delivery.

## References

- [Synchronization primitives — Python asyncio](https://docs.python.org/3/library/asyncio-sync.html#asyncio.Semaphore) — `Semaphore` semantics and use with `async with`
- [db.collection.bulkWrite() — MongoDB Manual](https://www.mongodb.com/docs/manual/reference/method/db.collection.bulkWrite/) — ordered vs unordered execution and upsert behaviour
- [asyncio.gather — Python docs](https://docs.python.org/3/library/asyncio-task.html#asyncio.gather) — eager scheduling, and why concurrency must be limited separately
