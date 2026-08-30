<!-- Reference, not instruction. Deliberately NOT in CLAUDE.md: it is derivable from the
codebase, and CLAUDE.md is loaded into every session whether it is needed or not. -->

# API surface

All under `/api`. Route order matters in FastAPI: `/sessions/tags` is declared **before**
`/sessions/{session_id}`, or `tags` would be read as an id.

```
GET    /api/health

GET    /api/cards ?q &format &category &ace_spec_only &page &page_size
                                           one printing per basic energy, newest plain one first
GET    /api/cards/{card_id}

POST   /api/decks/import                   creates a deck from PTCG Live text;
                                           declared BEFORE /{deck_id} or "import" reads as an id
GET    /api/decks/{id}/export               the list as text/plain, ready to paste

GET    /api/decks                          list with validation state
POST   /api/decks                          creates the deck and its empty v1
GET    /api/decks/{id}
PATCH  /api/decks/{id}                     name, icons, folder_id
DELETE /api/decks/{id}                     409 if any session used it
PUT    /api/decks/{id}/cards               replaces the current version's list (idempotent)
POST   /api/decks/{id}/versions            freezes the current list, opens a new version
GET    /api/decks/{id}/versions
GET    /api/decks/{id}/versions/{vid}
GET    /api/decks/{id}/stats ?date_from &date_to &session_type &tag

GET    /api/sessions ?tag
POST   /api/sessions
GET    /api/sessions/tags                  distinct tags with counts — declared before /{id}
GET    /api/sessions/{id}
PATCH  /api/sessions/{id}
DELETE /api/sessions/{id}
POST   /api/sessions/{id}/matches          appends a round, server assigns its number
PUT    /api/sessions/{id}/matches/{round}
DELETE /api/sessions/{id}/matches/{round}  renumbers the remaining rounds

GET    /api/folders                        flat; the client assembles the tree
POST   /api/folders
PATCH  /api/folders/{id}                   rename or move; 400 if the move would close a cycle
DELETE /api/folders/{id}                   children re-parent upward, nothing is deleted

GET    /api/pokemon ?q &limit
```

## Deck validation shape

`DeckValidation.violations` is a list of `{code, params, card_ids}`. `code` is a
`ViolationCode` wire value (`wrong_size`, `too_many_copies`, `too_many_ace_spec`,
`illegal_in_format`, `unknown_card`); `params` carries only the numbers and names
each sentence needs (counts, a card name, the declared format, a sample of up to
three illegal card names). There is no `message` field — the backend does not
render a sentence at all. The words live in the frontend's `violation.*`
catalogue (`frontend/src/i18n/`), keyed by `code`; the client picks the string
and interpolates `params` into it. This is deliberate: a rendered `message`
alongside `params` would be two sources of truth for one sentence, and the day
the Spanish text changes and the English `message` does not, nobody notices.
