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

**Card data source: [TCGdex](https://tcgdex.dev/).** No API key, official Python SDK, open source,
includes card images, and serves 12+ languages. Rejected `pokemontcg.io` — it has been folded into
the commercial Scrydex product and its public endpoint has been measured around 39% reliability.
TCGdex has no pricing data; nothing in the planned feature set needs prices.

**All external card calls go behind one adapter module** (`backend/app/services/card_source.py`), and
the rest of the codebase depends on our own card model rather than TCGdex's response shape. This
keeps a provider swap to one file. It is also the lesson: isolate what you don't control.

## Domain model (draft)

- **Match** — one recorded game: date, opponent archetype, deck version played, result, notes.
- **Deck** — a named deck owned by the user. Not a single card list — a list *plus a history*.
- **DeckVersion** — a snapshot of the card list at a point in time with a message describing the
  change, like a Git commit. **Matches reference the version played, not just the deck**, so win
  rates can be attributed to specific builds. This is the central design idea of the app; retrofitting
  version references onto existing match records later is painful.
- **Archetype** — the opponent's deck type. Not available from any API; user-maintained. A controlled
  list produces far better statistics than free text.
- **Matchup** — derived at query time, not stored: matches grouped by (deck version, archetype).

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

None yet. Add them here only after they have actually been run — an unverified command is worse than
no command.

## Status

Greenfield. Scaffolding only: this file, `README.md`, `.gitignore`, and `.claude/skills/`. Git repo
initialised; no application code yet. Next: phase 1 of the roadmap.
