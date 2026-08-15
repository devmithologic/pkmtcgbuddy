<!-- Reference, not instruction. Deliberately NOT in CLAUDE.md, which is loaded into every
session whether it is needed or not. CLAUDE.md carries a one-line index of what is here;
read this file before proposing architecture, choosing a provider, or reopening a settled
question. -->

# Commands

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

# Sync the set abbreviations (MEG, TEF, PRE…) from TCGdex. ~4 s, 218 requests.
# REQUIRED for deck import/export: the abbreviation is not in the card id.
cd backend && source .venv/bin/activate && python -m app.services.set_sync

# Sync the Pokedex from PokeAPI: 1,351 entries, one request, ~0.6 s.
# Needed once; re-run only when a new generation ships.
cd backend && source .venv/bin/activate && python -m app.services.pokemon_sync

# Inspect stored documents. There is NO `matches` collection — rounds live inside sessions.
mongosh pkmtcgbuddy --eval 'db.getCollectionNames()'
mongosh pkmtcgbuddy --eval 'db.sessions.find().pretty()'
mongosh pkmtcgbuddy --eval 'db.cards.countDocuments()'
```

Seven collections: `cards` (~15k), `pokemon` (1,351), `sets` (188), `decks`, `deck_versions`, `sessions`, `folders`.
The last four hold the user's own data and are small — single digits — which is why several
repositories fetch them whole and work in memory.

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

Phases 1–4 are built and verified in the browser.

- **Phase 1** — record and list play. Now grouped into *sessions* rather than loose matches.
- **Phase 2** — card search served from our own Mongo (~15k Expanded cards) with format, category and
  ACE SPEC filters; decks with version history, legality validation, and folders.
- **Phase 3** — TCGdex and PokeAPI, both behind one adapter each, both synced rather than called live.
- **Phase 4** — deck statistics: overall record, by version, by archetype, by session type, with
  date/type/tag filters. `db/stats_repository.py`, one aggregation.

Known gaps, in the order they are likely to matter:

- **No tests.** Phase 5 has not started. Everything so far was verified by hand in the browser and
  with scripted API calls — real, but not repeatable.
- **Two review findings left open** (documented in commit `454f001`): round numbers use
  read-modify-write, which only matters under concurrency and this is a single-user local app; and
  saving a deck containing cards outside the synced catalogue silently drops them.
- **Deck deletion is blocked, not cascading**, when sessions reference the deck. Deliberate, but it
  means a deck can only be removed after its sessions are.
- Pokémon display names are raw PokeAPI slugs: `lucario-mega`, `dudunsparce-two-segment`.
- No drag-and-drop for folders, and no depth limit on the tree.
- Advanced card search (trainerType, stage, types) would need a re-sync to store those fields.

`log_mentor/` is the learning record and the point of the repo; check the folder for the current
count. Entries are written by the `log-mentor` skill, which dispatches a Haiku subagent — see below.

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
