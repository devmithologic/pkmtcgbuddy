# pkmtrainerproject

## What this project is for

**The primary goal is for the developer to learn full-stack web development**, as a deliberate step
toward adding full-stack engineering to their career. The application is the vehicle, not the point.

The application being built is a **Pokémon TCG companion**: record matches, manage decks with
version history, and analyze matchups and statistics.

This ordering matters and should drive every decision in this repo. When "ship it faster" and
"understand it properly" conflict, **understanding wins**. A feature that works but whose mechanism
is opaque to the developer is a failed feature here, even though it would be a success in a normal
project.

## How Claude should work on this project

These are not stylistic preferences — they are the point of the project. Follow them.

### Teach, don't just deliver

- **Explain before and while writing code.** Say what the piece does, why it's structured that way,
  and what would break without it. Code with no explanation is a missed lesson.
- **Use real industry names for things.** Say *dependency injection*, *DTO*, *repository pattern*,
  *CORS preflight*, *N+1 query*, *optimistic UI*. The vocabulary is half the skill — it's what makes
  documentation searchable and interviews answerable.
- **Connect to the wider practice.** When something is a common industry pattern, say so. When
  something is a shortcut we're taking, say that too, and describe what the production version looks
  like.

### Let the developer do the work that teaches

- **Hand over the interesting parts.** For code that carries a new concept, prefer explaining the
  shape and letting the developer write it, then reviewing. Claude should write the boilerplate and
  the repetitive parts.
- **When they ask "how do I…", answer the question — don't silently do it for them** unless they
  asked for it to be done.
- **Don't silently correct their mistakes.** Point out what's wrong, explain why it's wrong, and let
  them fix it. A bug they debug themselves is worth more than ten they never saw.

### Build in vertical slices

Build **one feature end-to-end** — MongoDB → FastAPI → React → visible in the browser — before
starting the next. Do **not** build the entire backend and then the entire frontend.

Slices teach how the layers connect, produce something runnable at every step, and surface
integration problems (CORS, serialization, async, error shapes) early, while they're still small.

### Keep it small and honest

- **Build only what the current step needs.** No speculative abstraction, no "we'll need this later."
- **Prefer the plain approach over the clever one.** Clever code is bad teaching material.
- **No magic libraries.** Don't introduce a tool that hides a mechanism the developer hasn't
  understood yet. Understand the manual version first, then adopt the shortcut deliberately.
- **Present real trade-offs and let the developer choose** the meaningful ones — embed vs. reference
  in Mongo, client vs. server state, where validation lives. Give a recommendation, but make it their
  call.

### Check in

At the end of a slice, briefly recap what was built, what concept it demonstrated, and what's next.
It's fine — encouraged — to ask whether something landed before building on top of it.

## Learning roadmap

Rough sequence, not a contract. Each phase should end with something that runs.

| Phase | Build | Concepts it teaches |
| ----- | ----- | ------------------- |
| 1. First slice | Record a match; list matches | HTTP, REST, JSON, async Python, React state, fetch, CORS |
| 2. Real domain | Decks and deck versions | Data modeling, relationships in a document DB, migrations-by-hand |
| 3. External data | Card lookup via TCGdex | Third-party APIs, adapters, caching, sync jobs, failure handling |
| 4. Analysis | Matchup + win-rate stats | Aggregation pipelines, derived data, charting |
| 5. Quality | Tests, validation, error handling | pytest, Pydantic validation, HTTP error semantics |
| 6. Containerize | Docker + docker-compose | Images, layers, service networking, env config |
| 7. Deploy *(stretch)* | Put it online | CI, secrets, production config |

## Stack

| Layer    | Choice           | Notes                                          |
| -------- | ---------------- | ---------------------------------------------- |
| Frontend | React            | Vite as the build tool unless decided otherwise |
| Backend  | FastAPI (Python) | Pydantic models, async endpoints                |
| Database | MongoDB          | The "M" in FARM                                 |
| Card data| TCGdex           | See decision below                              |
| Deploy   | Docker           | Deliberately deferred to phase 6                |

## Decisions made

**Card data source: [TCGdex](https://tcgdex.dev/).** No API key, open source, includes card images,
and serves 12+ languages. Rejected `pokemontcg.io` — folded into the commercial Scrydex product, and
measured at 1 successful request in 10 on 2026-08-09.

Correction to an earlier note here: TCGdex *does* expose pricing (`cardmarket` and `tcgplayer`,
updated daily). The original claim that it had none is no longer true. Nothing in the feature set
needs prices yet, so we do not store them.

**MongoDB driver: `pymongo.AsyncMongoClient`, not Motor.** Motor was the async MongoDB driver for
years, but it has been superseded — MongoDB's own docs now publish a *"Migrate From Motor"* page, and
async support lives inside `pymongo` itself. Motor also carries a thread pool for network operations
that `AsyncMongoClient` does without. Anything on the web recommending `motor.motor_asyncio` predates
this.

**Second external provider: PokeAPI**, for Pokémon sprites — the icons that identify a deck
("Dragapult / Dusknoir") and each round's opponent. Same containment as TCGdex:
`services/pokemon_source.py` is the only file that knows it exists, and it composes the sprite URL so
a provider change is one line. All 1,351 PokeAPI entries are synced once with `python -m app.services.pokemon_sync` (0.6 s);
nothing is fetched live. That is the 1,025 national dex **plus 326 forms** — including the 97 Mega
Evolutions, which the TCG needs now that Mega Evolution sets exist, plus Gigantamax and regional
variants.

The id comes from the resource URL, never from the list position. Deriving it from the index works
by coincidence for 1–1025 and breaks immediately above: Mega forms start at 10033.

Sprites are 1 KB each; the official artwork on the same host is 110–155 KB and is not an icon.

**Icons live on the deck and on each round**, never on the session — in a five-round tournament you
face five different decks. They coexist with the free-text `opponent_archetype` rather than replacing
it: "Lost Box" is defined by Comfey and Sableye, and some deck names are not a Pokémon at all.

**All external card calls go behind one adapter module** (`backend/app/services/card_source.py`), and
the rest of the codebase depends on our own card model rather than TCGdex's response shape. This
keeps a provider swap to one file. It is also the lesson: isolate what you don't control.

**Card data is synced into MongoDB, not fetched live.** The API serves searches from our own `cards`
collection; `card_source.py` is now called only by the sync job, never by a request.

The live proxy came first on purpose — understand the direct call before adopting the cache. On
2026-08-09 the TCGdex API was down for hours (TLS handshake timeout, then connection refused) and
card search stopped working entirely while our server and database were healthy. Measured
alternatives at the time: `pokemontcg.io` succeeded 1 request in 10 and lacks `regulationMark`;
Limitless has no cards endpoint at all, only tournaments and games; apitcg.com and Scrydex require
registration. No provider is reliable enough to depend on per request.

Syncing turns TCGdex from a runtime dependency into a deploy-time one. It also made searches ~600×
faster: 0.8 ms locally versus ~500 ms proxied.

**Card legality is per *card*, not per *printing*.** The tournament rule is that if a card is
reprinted in a legal set, older printings of the same card are legal too — a Boss's Orders from
Paldea Evolved (mark G) is playable because Mega Evolution reprinted it with mark I. TCGdex does not
model this: it reports legality per printing, so its mark-G copies come back illegal.

`card_sync` reconstructs the real rule in a second pass, grouping printings by a content signature
(`Card.identity`: name plus text, never set or rarity) and promoting a whole group if any member is
legal. Grouping by *name* would be wrong — 59 of the 65 cards named "Pikachu" are genuinely different
cards, and Poké Ball has three distinct versions, one of which flips a coin.

Known limit: Pokémon reworded card templates in the Scarlet & Violet era, so a card whose text was
rewritten does not group with its older printings. Measured: 26 Trainer/Energy names, 94 printings,
including Boss's Orders marks D and F. Matching those by name would wrongly legalise the coin-flip
Poké Ball, so the gap is left open deliberately.

**Sync scope is a real decision, and it is invisible at query time.** TCGdex holds 23,546 cards;
14,901 are Expanded-legal and 3,345 Standard-legal. Syncing `--format standard` omits promo printings
that are not Standard-legal — which looks like missing data from the provider until you check. Sync
Expanded: it is a superset of Standard. The database currently holds the full Expanded set.

**Substring search does not use an index.** `name` matching is an unanchored `$regex`, which has to
examine every candidate document. Measured: 0.8 ms over 3,318 cards, 6.1 ms over 14,901 — still ~80×
faster than the live proxy, but the cost grows with the collection. If it ever matters, the options
are a MongoDB text index (word-based, would stop `rod` matching `Aerodactyl`) or anchoring the
pattern to a prefix. Neither is worth doing yet.

## Domain model (draft)

- **Session** — one event: a league night, a Cup, an afternoon of testing. Holds the date, the
  session type (`league` · `cup` · `challenge` · `online` · `testing`), the deck version played, and
  its rounds. The deck lives here, not on the match — you pick a deck once when the tournament
  starts, not before every round.
- **Match** — one round inside a session: opponent archetype, result, notes. **Embedded** in the
  session document, unlike DeckVersion which is a separate collection. The criterion is the direction
  of the references: nothing outside a session points at an individual match, whereas a session does
  point at a deck version. The array is also bounded — a tournament is 4–9 rounds.
- **Record** — a session's W–L–T, derived at read time, never stored.
- **Deck** — a named deck owned by the user. Not a single card list — a list *plus a history*.
- **DeckVersion** — a snapshot of the card list at a point in time with a message describing the
  change, like a Git commit. **Matches reference the version played, not just the deck**, so win
  rates can be attributed to specific builds. This is the central design idea of the app; retrofitting
  version references onto existing match records later is painful.
- **Archetype** — the opponent's deck type. Not available from any API; user-maintained. A controlled
  list produces far better statistics than free text.
- **Matchup** — derived at query time, not stored: matches grouped by (deck version, archetype).
  Computed in `db/stats_repository.py` with `$match` → `$unwind` → `$facet`. `$unwind` turns a
  session's embedded rounds into one document each; `$facet` runs four groupings over that single
  read. **`$facet` cannot be nested** (`$facet is not allowed to be used within a $facet stage`), so
  the session count is a separate `count_documents` rather than a second branch.

## Planned layout

```
backend/
  app/
    main.py         ASGI entrypoint
    models/         Pydantic schemas
    routers/        One module per resource
    services/       Business logic, external adapters
    db/             Mongo client + collection access
  tests/
frontend/
  src/
    components/
    pages/
    api/            The only place that talks to the backend
```

## Conventions

Short and real. Add entries as they become true, delete ones that stop being true.

- Backend: type-annotated Python; Pydantic models at the API boundary.
- API: REST under `/api`, plural resource names (`/api/decks`, `/api/matches`).
- Frontend components never call `fetch` directly — all backend access goes through `src/api/`.
- Secrets in `.env`, never committed; `.env.example` documents the required keys.

## Commands

All verified. Three processes; MongoDB runs as a service, the other two need a terminal each.

```bash
# Backend — terminal 1
cd backend && source .venv/bin/activate && uvicorn app.main:app --reload   # :8000

# Frontend — terminal 2
cd frontend && npm run dev                                                 # :5173

# MongoDB — launchd service, starts at login. Aliases in ~/.zshrc:
mongo-status · mongo-ping · mongo-start · mongo-stop · mongo-log

# Sync the card catalogue from TCGdex into MongoDB. Run by hand, not on startup.
# Expanded by default because it is a superset of Standard.
cd backend && source .venv/bin/activate && python -m app.services.card_sync
python -m app.services.card_sync --format standard

# Inspect stored documents
mongosh pkmtcgbuddy --eval 'db.matches.find().pretty()'
mongosh pkmtcgbuddy --eval 'db.cards.countDocuments()'
```

`brew services start mongodb-community` does **not** work: the `mongodb/brew` tap uses the old service
format and Homebrew 6.x generates a plist with empty `ProgramArguments` (`Bootstrap failed: 5`). The
service is loaded into launchd directly from the formula's own plist.

First-time setup, after cloning:

```bash
cd backend && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && cp .env.example .env
cd ../frontend && npm install && cp .env.example .env
```

## Status

Phase 1 complete: a match can be recorded and listed end to end, verified in the browser.

Phase 2 is split in two slices. **Slice A is done**: card search with filters for format, category
and ACE SPEC, plus a detail panel. Served from MongoDB, not from a live TCGdex call — see the sync
decision above. 14,901 Expanded-legal cards synced; re-run `card_sync` to refresh.
`log_mentor/` holds fourteen entries.

**Next — phase 2, slice B: decks.** Agreed rules:

- 60 cards exactly; at most 4 copies of a card by name, basic Energy exempt.
- At most **1 ACE SPEC** per deck. Detected via `Card.is_ace_spec`, never by string matching.
- A deck declares a format (`standard` or `expanded`); every card must be legal in it.
- **Incomplete decks are saved anyway.** The API stores whatever state the deck is in and reports
  what makes it illegal. Building a deck is iterative; refusing to save until it is legal is the
  wrong shape. Keep input validation separate from these business rules.
- `DeckVersion` lands here, not later. Matches must reference the version played — retrofitting that
  onto existing records is the one thing `CLAUDE.md` warns about most.
