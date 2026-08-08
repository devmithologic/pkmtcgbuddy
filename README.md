# pkmtrainerproject

A Pokémon TCG companion: record matches, manage decks with version history, and analyze matchups
and win rates.

It is also, deliberately, a learning project. The goal is to learn full-stack web development by
building something real end to end — so the code favours the plain, explainable approach over the
clever one, and every new concept gets written up in [`log_mentor/`](log_mentor/).

## The idea

Most match trackers let you record *which deck* you played. This one records **which version** of
that deck you played.

A `Deck` is not a single card list — it is a list plus a history. Every change produces a
`DeckVersion`: a snapshot of the list with a message describing what changed, like a Git commit.
Matches reference the version, not just the deck. That makes it possible to ask questions a normal
tracker can't answer:

> The Gardevoir matchup was 30% before I cut the second Iono. What is it now?

## Stack

| Layer     | Choice           |
| --------- | ---------------- |
| Frontend  | React + Vite     |
| Backend   | FastAPI (Python) |
| Database  | MongoDB          |
| Card data | [TCGdex](https://tcgdex.dev/) |
| Deploy    | Docker           |

FastAPI + React + MongoDB is commonly called the **FARM stack**.

Card data comes from TCGdex: open source, no API key, official Python SDK, includes card images and
12+ languages. All calls to it go behind a single adapter module so the rest of the codebase depends
on our own card model rather than a third party's response shape.

## Domain model

- **Match** — one recorded game: date, opponent archetype, deck version played, result, notes.
- **Deck** — a named deck. A list *plus a history*.
- **DeckVersion** — a snapshot of the card list with a change message.
- **Archetype** — the opponent's deck type. No API provides these; the list is user-maintained.
- **Matchup** — derived at query time, never stored: matches grouped by (deck version, archetype).

## Layout

```
backend/     FastAPI app — models, routers, services, db
frontend/    React app — src/api is the only place that talks to the backend
log_mentor/  Learning notes, one concept per file
.claude/     Project instructions and skills for Claude Code
```

## Status

Early. Phase 1 works: a match can be recorded and listed, end to end.

The roadmap is built in vertical slices, one feature at a time from database to browser:

1. ~~Record a match; list matches~~ ✓
2. Decks and deck versions
3. Card lookup via TCGdex
4. Matchup and win-rate statistics
5. Tests, validation, error handling
6. Docker + docker-compose
7. Deploy

## Running it

Requires Python 3.12+, Node 20+, and a local MongoDB on `:27017`.

```bash
# One-time setup
cd backend && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && cp .env.example .env
cd ../frontend && npm install && cp .env.example .env
```

Then two terminals:

```bash
cd backend && source .venv/bin/activate && uvicorn app.main:app --reload   # :8000
cd frontend && npm run dev                                                 # :5173
```

The app is at `http://localhost:5173`; the generated API docs at `http://localhost:8000/docs`.
