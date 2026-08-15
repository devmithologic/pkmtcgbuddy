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

### Write the log, but don't write it yourself

The `log-mentor` skill **dispatches a subagent** (`.claude/agents/log-mentor.md`, `model: haiku`)
rather than writing the entry in the main conversation. Two reasons: 150 lines of reference prose
would eat the working session's context, and it is templated writing that does not need the most
expensive model.

The consequence to work around: **that subagent never saw the conversation.** It recovers the *why*
from `git diff`, from `docs/decisions.md`, and from the code comments — which in this repo explain
the failure a line prevents, not what the line does. If something only existed in
conversation — an alternative that was tried and rejected, a measurement taken and not written down —
say it in the dispatch prompt, because nothing else can.

## Conventions

Short and real. Add entries as they become true, delete ones that stop being true.

- Backend: type-annotated Python; Pydantic models at the API boundary.
- API: REST under `/api`, plural resource names (`/api/decks`, `/api/sessions`).
- Frontend components never call `fetch` directly — all backend access goes through `src/api/`.
- Secrets in `.env`, never committed; `.env.example` documents the required keys.
- **Separate the model that comes in from the model that goes out.** `Create`/`Update` versus `Out`,
  everywhere. It is not ceremony: it is what stops a `@computed_field` from being written back to
  Mongo by `model_dump()`, and what stops mass assignment.
- **Never enumerate fields by hand** when passing a whole object through. `**payload.model_dump()` on
  the backend, the whole object on the frontend. Enumerating has silently dropped data twice — round
  icons in `add_match`, deck icons in `createDeck` — because a filter written once is not updated when
  the model grows. The backend's model is what decides which fields are valid.
- **PATCH means `exclude_unset`.** Distinguish "the client did not send this" from "the client sent
  null". Which one null *means* differs per field and must be decided per field: null `name` is
  client noise and is dropped; null `folder_id` and null `parent_id` are instructions.
- Comments explain the mechanism and the failure they prevent, not what the line does. The repo is a
  learning artifact; a comment restating the code is dead weight, and a comment naming the bug that
  bit us is the whole point.
- Code and comments are written in Spanish; `CLAUDE.md` and `log_mentor/` in English. Do not mix
  within a file.

## Before you act: read the decision record

Everything that was below the guidelines has moved out of this file. It is history and reference —
valuable, but it does not need to be in context before you have done anything. What stays here is the
index, so you always know a decision **exists** on a topic and can go read why.

**`docs/decisions.md`** — the stack, and the reasoning behind every choice. Read it before proposing
an architecture, swapping a provider, or reopening any of these:

| Decision | Why, in short |
| --- | --- |
| Card data comes from TCGdex | `pokemontcg.io` measured at 1 successful request in 10 |
| Driver is `pymongo.AsyncMongoClient` | Motor is superseded; anything recommending it is stale |
| Pokémon sprites come from PokeAPI | second provider, same containment as the first |
| Two image sets, chosen by measurement | small icon for dense lists, HOME render for headings |
| The image URL is derived, never stored | it is a provider detail, not immutable data |
| Icons live on the deck and on each round | in a five-round tournament you may not play one deck |
| Cards are synced into Mongo, not fetched live | TCGdex was down for hours on 2026-08-09 |
| Every external call sits behind one adapter | `card_source.py`, `pokemon_source.py` |
| Legality is per card, not per printing | a reprint makes older printings legal too |
| Sync scope is Expanded | it is a superset of Standard |
| Substring search does not use an index | measured, and deliberately left alone |
| A `<button>` cannot contain interactive content | Space activated the button instead of typing |
| One `Menu` component for every popover | the only `document` listener in the app |
| Deck lists import/export as PTCG Live text | the interop format; needs the `sets` collection |
| Import takes what it resolves and reports the rest | a friend's list may cite an unsynced set |

**`docs/domain.md`** — Session, Match, Record, Tags, Deck, DeckVersion, Folder, Archetype, Matchup,
and the deck legality rules. Read it before touching a model or adding a field. It also holds three
decisions that are about the shape of the domain rather than the stack, so look for them here and
not in the table above:

| Decision | Why, in short |
| --- | --- |
| Deck folders are a tree of parent references | chosen for collection size, not elegance |
| Deleting a deck is refused if sessions used it | 409, never a cascade |
| Width is chosen per content type | `--shell` caps the page, `--measure` caps forms |

**`docs/architecture.md`** — what each file is for; the dependency points routers → services → db →
models. Read it before adding a module or when you cannot find where something lives.

**`docs/api.md`** — the 29 endpoints across five routers, their parameters and their non-obvious
responses. Read it before touching `routers/` or `frontend/src/api/`.

**`docs/operations.md`** — how to run everything, the sync jobs, the current status and the known
gaps. Read it first if you need to start the app or check what is already built.

Keep them current when the shape changes: a stale map is worse than no map, and this table must gain
a row when a new decision is made.
