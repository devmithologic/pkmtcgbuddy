# Runtime vs Deploy-Time Dependencies

> **Stack:** HTTP · **Introduced in:** the TCGdex outage of 2026-08-09 · **Date:** 2026-08-09

## Definition

A **runtime dependency** is a system your application calls while serving a request: if it is down,
your feature is down. A **deploy-time dependency** is one you call before serving traffic — during a
build, a migration, or a sync job — so its availability affects deployments, not users.

Moving a dependency from the first category to the second is usually the cheapest reliability win
available.

## Why it matters

Availability multiplies. A service at 99.9% that calls one dependency per request cannot exceed the
dependency's uptime; call two independent ones and the ceiling is roughly 99.9% × 99.9%. Every
runtime dependency is a term in that product.

This is not theory here. On 2026-08-09 the TCGdex API stopped answering — TLS handshakes timing out,
later refusing connections outright. Card search returned nothing for hours. Our server was healthy,
MongoDB was healthy, matches worked in 7 ms. One third party's outage was our outage, because we had
chosen to ask them a question on every keystroke.

The instinctive fix is to find a better provider. Measured that day:

| Provider | Result |
| --- | --- |
| TCGdex | down |
| pokemontcg.io | 1 of 10 requests succeeded; missing `regulationMark` |
| Limitless | no cards endpoint at all — tournaments and games only |
| apitcg.com, Scrydex | up, require registration |

There was no better provider. There rarely is: switching only changes the date of the next outage.
The dependency *direction* was the problem, not the vendor.

## How it works

Ask what the dependency actually provides, and how often it changes:

- **Data that changes per request** — a payment authorisation, someone else's live inventory — must
  be a runtime dependency. There is no alternative.
- **Data that changes slowly** — a card catalogue, currency codes, a product list — does not. Copy it
  into your own store on your own schedule, and serve from there.

The move has a shape:

1. Keep the adapter that talks to the third party.
2. Add local storage with the same interface.
3. Point request handling at the local store.
4. Have a job fill it (`see 13_PYTHON_BATCH_JOBS.md`).

What you gain: the feature survives their outage, latency collapses, and their rate limits stop
mattering. What you pay: the data goes stale, and staleness is now yours to manage.

That trade is the whole decision. It is worth making when data changes on the order of days and
wrong when it changes on the order of seconds.

## In this project

Before, every search was a live call:

```
browser → our API → TCGdex → our API → browser        ~500 ms, fails when they fail
```

After:

```
browser → our API → MongoDB → browser                 ~0.8 ms, unaffected by their uptime
sync job → TCGdex → MongoDB                           run by hand, roughly once a week
```

The router stopped importing the adapter entirely:

```python
# backend/app/routers/cards.py
from app.db import card_repository     # was: from app.services import card_source
```

And the web process no longer opens an HTTP client at all:

```python
# backend/app/main.py — lifespan
await connect_to_mongo()
await card_repository.ensure_indexes()
yield
await close_mongo_connection()
# no connect_card_source(): nothing outside is consulted while serving a request
```

Measured effect: search went from ~500 ms to **0.8 ms**, roughly 600× — the latency was never
computation, it was a round trip to Canada.

Note what did *not* change: `card_source.py`, untouched. The adapter was written on the claim that it
would confine a provider swap to one file (`see 07_PYTHON_ADAPTER_PATTERN.md`). This is the
counter-check — not swapping the provider, but changing *when* it is called — and it cost two
imports.

**The order mattered.** The live proxy was built first on purpose: understand the direct call before
adopting the cache. Had we started with syncing, the sync would have been cargo cult. Starting with
the proxy meant the outage supplied the argument, and the cache became a decision instead of a habit.

## Gotchas

- **Staleness is real and now yours.** Standard held 3,318 cards when synced and 3,345 the next day.
  Twenty-seven cards were invisible until the next run. The live proxy never had this problem — it
  traded it for the outage.
- **Distinguish "empty" from "never synced".** A fresh deploy with no data looks identical to a search
  with no matches. Our API returns `503` with the command to run, rather than an innocent empty list.
- **A cache does not remove the dependency, it moves it.** The first sync still needs them up. During
  the outage we could not have populated an empty database.
- **Scope the copy deliberately.** Syncing `--format standard` fetched 3,345 of TCGdex's 23,546
  cards. Promo cards outside Standard were then missing — and that looked like a gap in *their* data
  until we checked. A filter chosen at sync time is invisible at query time.
- **The reverse mistake exists.** Caching data that genuinely changes per request serves wrong
  answers confidently, which is worse than an outage.

## Related concepts

`see 07_PYTHON_ADAPTER_PATTERN.md` — what made the switch cheap;
`see 13_PYTHON_BATCH_JOBS.md` — the job that fills the store; graceful degradation; circuit breakers,
which limit a runtime dependency you cannot eliminate; cache invalidation.

## References

- [Availability in series — Google SRE Book, "Embracing Risk"](https://sre.google/sre-book/embracing-risk/) — how dependency availability multiplies, and how to reason about error budgets
- [503 Service Unavailable — MDN](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/503) — the status for "temporarily unable to serve", used here for an unsynced catalogue
- [Cache-Aside pattern — Microsoft Azure Architecture Center](https://learn.microsoft.com/en-us/azure/architecture/patterns/cache-aside) — the general shape of moving reads off a slow or unreliable source
