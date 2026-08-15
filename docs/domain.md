<!-- Reference, not instruction. Deliberately NOT in CLAUDE.md, which is loaded into every
session whether it is needed or not. CLAUDE.md carries a one-line index of what is here;
read this file before proposing architecture, choosing a provider, or reopening a settled
question. -->

# Domain model (draft)

- **Session** — one event: a league night, a Cup, an afternoon of testing. Holds the date, the
  session type (`league` · `cup` · `challenge` · `online` · `testing`), the deck version played, and
  its rounds. The deck lives here, not on the match — you pick a deck once when the tournament
  starts, not before every round.
- **Match** — one round inside a session: opponent archetype, result, notes. **Embedded** in the
  session document, unlike DeckVersion which is a separate collection. The criterion is the direction
  of the references: nothing outside a session points at an individual match, whereas a session does
  point at a deck version. The array is also bounded — a tournament is 4–9 rounds.
- **Record** — a session's W–L–T, derived at read time, never stored.
- **Tags** — free-text labels on a session: the store, the purpose, whatever groups it. Normalised on
  write (lowercased, trimmed, deduped) because the risk is drift — "GameSmart", "gamesmart" and
  "Game Smart" becoming three tags is the same failure as free-text archetypes. Filter the session
  list and the deck stats.

  Note the contrast with **season**, which is deliberately *not* a tag: a season is a date range and
  `played_at` already holds it, so a tag could contradict it. Tag what the data cannot express;
  derive what it can.
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

**Width is chosen per content type, not once for the app.** Two tokens in `index.css`: `--shell`
(90rem) caps the container, `--measure` (34rem) caps forms and prose. Lists and grids take what's
left.

The app used to live entirely inside `max-width: 42rem`. That number is the classic *reading
measure* — roughly 70 characters, the width at which the eye finds the next line reliably — and it is
right for a paragraph or a form. It is wrong for a five-column session row or a grid of card images,
where the constraint is not the line, it's how much fits. Measured on a 1720px screen: the app used
630px, 37% of the width, and the card grid gave 4 columns where 9 fit.

The tell was already in the CSS: `.app:has(.deck-builder) { max-width: 68rem }`. The builder wasn't a
special case — it was the first screen to ask for the width all of them needed. **An exception that
repeats is not an exception.**

Capped rather than fluid on purpose: at full width a session row is 1700px, with the date at one end
and the record at the other.

Two layout rules that follow from it:

- `.screen-split` puts the create-form beside the list instead of above it, reusing the two-column
  shape `.builder-cols` already had. `.screen-split--end` is the same grid with the narrow column on
  the right, for the session detail — moving a column is the grid's job, and inverting the DOM to get
  it would have broken tab and screen-reader order for nothing.
- Both columns are `minmax(0, …)`. Without the zero minimum, a child that doesn't fit widens its
  column and overflows the grid instead of shrinking — the classic CSS Grid trap.

**Icon lanes are fixed-width** (`.pkm-slot`). `PokemonPair` returns `null` when a deck or opponent has
no Pokémon, and a deck may have one icon or two, so without a reserved lane the grid cell vanishes and
each row starts its name somewhere different. A list is scanned down its left edge.

**Deck folders are a tree, modelled with parent references.** MongoDB documents five ways to store a
tree; they differ in which query they make cheap. Parent references make walking *up* trivial and
walking *down* expensive; an ancestors array or a materialized path make the subtree query one indexed
lookup, but every move rewrites all descendants.

Parent references win here for a reason that is about size, not elegance: a user has five or ten
folders, so `folder_repository` fetches the whole collection in one query and assembles the tree in
memory. The query that this model makes expensive is never issued. The other four patterns exist for
collections too big to fetch — at ten documents they would be machinery to speed up something already
instant. `$graphLookup` is not used anywhere.

**The cycle check is what makes it a tree and not a graph.** Moving a folder into its own descendant
leaves both outside the tree — neither hangs off a root any more — so they vanish from the listing
without being deleted, and walking the cycle to render them hangs the browser. `crearia_ciclo()` walks
up from the proposed parent; if it meets the folder itself, the move is rejected with a 400. It runs
**before** the write: check-then-write needs no undo. The UI also omits impossible destinations from
the menu, but that is courtesy — the server is the authority.

**Decks are browsed, not displayed as a tree.** The screen shows one folder at a time with a
breadcrumb, like a file manager. Two consequences that paid for the change: what you create is created
*where you are*, so the deck form needs no folder selector — asking again for what the navigation
already says; and the "Sin carpeta" pseudo-group disappears, because the root already *is* that place.

**Deleting a deck is refused (409) if any session was played with it**, and the message says how many.
Not generic caution: the central idea of the app is that a match is attributed to the deck *version*
played, so deleting the deck would leave those sessions pointing at nothing. The record would survive
but no longer say which list it belonged to — exactly the data the app exists to keep. Cascading would
be deciding the most destructive option on the user's behalf.

**Deleting a folder never deletes decks.** Its subfolders and decks are re-parented to its own parent,
the way a file manager behaves when you ungroup. A folder at the root leaves its children at the root.

`folder_id` on a deck follows the `parent_id` rule, not the `name` rule: **`None` is a meaningful
value** — "take it out of its folder" — so `exclude_unset` must preserve it, while a null `name` can
only be client noise and is dropped. Both live in the same `update_*` function; the contrast is the
point.

## Deck legality rules

Implemented in `services/deck_rules.py` as a pure function — no I/O, no framework — so it can be
read and tested in isolation.

- 60 cards exactly; at most 4 copies of a card **by name**, basic Energy exempt.
- At most **1 ACE SPEC** per deck. Detected via `Card.is_ace_spec`, never by string matching.
- A deck declares a format (`standard` or `expanded`); every card must be legal in it.
- **Incomplete decks are saved anyway.** The API stores whatever state the deck is in and reports what
  makes it illegal, as a list of `Violation` objects carrying a code, a message and the card ids.
  Building a deck is iterative; refusing to save until it is legal is the wrong shape. Input
  validation and these business rules stay separate.
- `DeckValidation` is computed at read time and never stored — same rule as `Matchup` and the record.
