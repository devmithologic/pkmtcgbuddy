<!-- Reference, not instruction. Deliberately NOT in CLAUDE.md, which is loaded into every
session whether it is needed or not. CLAUDE.md carries a one-line index of what is here;
read this file before proposing architecture, choosing a provider, or reopening a settled
question. -->

# Stack

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

**Two image sets, chosen by measurement.** Sampling 150 of the 1,351 synced ids:

| set | found | Megas | median | pixels |
| --- | ----- | ----- | ------ | ------ |
| `sprites/pokemon/` | 148 | 63/65 | 1.2 KB | 96×96 |
| **`other/home/`** | **148** | **63/65** | **124 KB** | **512×512** |
| `other/official-artwork/` | 147 | 62/65 | 125 KB | 475×475 |
| `versions/generation-viii/icons/` | 81 | 27/40 | 0.5 KB | 68×56 |

HOME has *exactly* the coverage of the small sprite — the two gaps, 10159 and 10264, are missing from
both — and Megas included. Official artwork weighs the same and is worse framed. The Sword/Shield box
icons are the right size but lose a third of the Megas: they don't exist in that game.

Both are used, because one set can't do both jobs. `icon_url` (1.2 KB) goes where images are dense —
the 20 picker results, each round of a session; `art_url` (HOME) goes where the image *is* the
heading — deck screen, deck list. Twenty HOME renders in a search box would be 2.5 MB.

**The URL is derived, never stored.** `PokemonRef` holds `dex_id` and `name`; `PokemonRefOut`
computes both URLs at read time. It used to store `sprite_url`, justified by "the data is immutable" —
true of the id and the name, false of the URL, which is a provider detail. Storing it copied the
provider into every deck and session document, so `pokemon_source.py`'s promise that a provider swap
is one line was quietly false: changing the constant would not have touched a single already-recorded
round. Deriving it fixed all of them with no migration; Pydantic ignores the stale `sprite_url` keys.

Same rule as tags, seen from the other side: **store what the data cannot express, derive what it can.**

Two mechanical consequences worth remembering:

- The computed fields live on a *subclass*, not on `PokemonRef`. `model_dump()` **includes** computed
  fields, and rounds are written with `**match.model_dump(mode="json")` — putting them on the input
  model would push the URLs straight back into Mongo.
- `pokemon_source.py` no longer imports `PokemonRef` (`fetch_all` returns plain dicts, `pokemon_sync`
  builds the models). Otherwise model → adapter → model is a circular import and the app won't start.

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

`card_sync` reconstructs the real rule in a second pass, promoting a whole group if any member is
legal. **What counts as "the same card" depends on the category, because the game's own rule does.**

- **Pokémon group by content signature** (`Card.identity`: name plus text and attacks, never set or
  rarity). Grouping them by name would be wrong — 59 of the 65 cards named "Pikachu" are genuinely
  different cards, and by measurement 1,235 Pokémon names carry more than one signature.
- **Trainer and Energy group by name**, with TCGdex's art suffix stripped: `Boss's Orders (Giovanni)`
  is Boss's Orders, and the parenthesis is the provider's, not the card's.

The Trainer/Energy half replaced signature grouping on 2026-08-15, and the reason it could is worth
recording. Signature grouping left a documented gap: Pokémon reworded the card templates in the
Scarlet & Violet era, so `Switch 1 of your opponent's Benched Pokémon with their Active Pokémon` did
not group with `Switch in 1 of your opponent's Benched Pokémon to the Active Spot` — the same card.
Measured at the time of the fix: **25 names, 192 printings**, including the Boss's Orders that a real
deck in this app was being told was illegal.

The gap had been left open because matching by name would have legalised the coin-flip Poké Ball.
**That blocker expired**: all three Poké Ball printings flip a coin, including the currently legal one
(`me03-080`, Mega Evolution). The game reprinted the coin-flip version, so it is the legal one.

Normalising the text instead — quotes, capitalisation, `Colorless` versus `{C}` — was measured and
rejected: it merges 2 of the 25 names. The other 23 are real rewrites, not typography.

Why name is the right key for a Trainer and not for a Pokémon: two Trainers with the same name cannot
be legal at once, and the rules say an older printing is played **with the current text**. So a
difference in wording does not make it a different card. A Pokémon's attacks do.

**Sync scope is a real decision, and it is invisible at query time.** TCGdex holds 23,546 cards;
14,901 are Expanded-legal and 3,345 Standard-legal. Syncing `--format standard` omits promo printings
that are not Standard-legal — which looks like missing data from the provider until you check. Sync
Expanded: it is a superset of Standard. The database currently holds the full Expanded set.

**The card search offers one printing of a basic energy, and it is the newest ordinary one.**
The deck builder was showing gold secret rares where the basic energies should be, and the reason was
not the interface. TCGdex names the secret rare `Basic Metal Energy` and the ordinary one
`Metal Energy`, so an alphabetical sort put the gold one first — always, whatever its date or rarity.
Every deck version already stored had hyper rares inside it. They were not chosen; they were the only
ones visible. Those decks are left alone: they are legal and they export correctly.

Three derived fields fix it, and each one earns its place:

- `sort_name` — the name without the `basic ` prefix, and **only** for basic energies, so the secret
  rare sorts inside the same group instead of winning the alphabet. `Basic Research Note` is not a
  reprint of anything.
- `printing_rank` — `0` for an ordinary printing, `1` for a secret one. Scoped to basic energies on
  purpose: for a real card the printing you pick is a legitimate choice, because the art matters. For
  a basic energy it is the same card with a better photo.
- `set_release_date` — copied from the `sets` collection, because `$lookup` cannot feed an indexed
  sort.

The order is `sort_name ASC, printing_rank ASC, set_release_date DESC, _id ASC`, and the compound
index matches it field by field and direction by direction — otherwise Mongo sorts in memory against a
32 MB ceiling. The trailing `_id` is the total order that keeps pagination deterministic.

Ordering alone was not enough: 313 of the 322 basic-energy printings are now **hidden**
(`is_energy_duplicate`), leaving the 9 that are current. And **the field you filter on is not the
field you sort on.** With the duplicates hidden, searching `basic` returned nothing at all — the gold
ones were gone and the plain ones are not called "basic". Hence `search_name`, which keeps the prefix
that `sort_name` removes. That was found by checking the result, not by thinking about it.

**A card with no image borrows one from another printing of the same card.** The whole `sve` set — the
24 current basic energies — has `image: null` in TCGdex; verified against their API, not deduced.
Across the collection, 1,035 of 15,021 cards have no image and 566 of those have a reprint that does.
The borrowed URL is chosen by the same criterion as the sort, and it is **derived at read time, never
stored**: storing it would copy into 566 documents a value belonging to another, exactly the mistake
already made once with the Pokémon sprites. The cost is one extra query per page of results, not one
per card — the ids without an image are collected and resolved with a single `$in`.

**Substring search does not use an index.** `name` matching is an unanchored `$regex`, which has to
examine every candidate document. Measured: 0.8 ms over 3,318 cards, 6.1 ms over 14,901 — still ~80×
faster than the live proxy, but the cost grows with the collection. If it ever matters, the options
are a MongoDB text index (word-based, would stop `rod` matching `Aerodactyl`) or anchoring the
pattern to a prefix. Neither is worth doing yet.

**A `<button>` cannot contain interactive content, and the browser does not warn you.** Inline rename
put an `<input>` inside the row's button. HTML forbids it, so behaviour is undefined — and Chrome's
choice is to activate the button when **Space** is pressed, regardless of where focus is. Typing a
folder name with a space in it navigated into the folder instead. There was nothing to intercept:
Space and Enter activate a button *by definition*, which is how it works without a mouse. The fix is
structural — `DeckList` renders a `<button>` normally and a `<div>` while renaming, both classed
`.row-main` so CSS does not care which.

Generalise from it: **when an element misbehaves under the keyboard, check the content model before
reaching for an event handler.** Suppressing the default would have broken keyboard use everywhere.

**One `Menu` component for every popover** (`components/Menu.jsx`). It started as the `⋮` of a list
row and grew a `trigger` prop when the `+ Nuevo` button needed the same behaviour — hence the generic
name; calling it `RowMenu` once it no longer lived only in a row would have been a lie.

It is the only place in the app that listens on `document`, because the click that closes it happens
outside the component and no React handler can see it. Two rules that listener imposes: it is
registered **only while the menu is open**, and its `useEffect` **returns its cleanup** — without that,
every open leaks a listener. It uses `mousedown` rather than `click` so the menu closes on press
instead of on release.


## Deck lists travel as PTCG Live text

The text format that PTCG Live exports and every online builder accepts is the interoperability
format, so it is the one we speak:

```
Pokémon: 17
3 Riolu PRE 50
```

Each line is `<quantity> <name> <ABBREVIATION> <number>`. Three things had to be solved before a real
list would resolve, and each was found by trying the user's own 60-card list:

1. **The abbreviation is not in the card id.** `MEG 77` is `me01-077` for us. TCGdex exposes
   `abbreviation.official` per set, but only on the per-set endpoint, so `services/set_sync.py`
   fetches all 218 and stores the 188 that have one in a `sets` collection.
2. **The card id must be split on the LAST dash.** 21 set ids contain dashes (`tk-ex-latia`), so
   `rpartition('-')`, never `split('-')`.
3. **Numbers are zero-padded in TCGdex and bare in the text format.** `me01-077` vs `MEG 77`. Rather
   than re-sync 15k cards with a normalised field, `candidate_ids()` generates the padding variants
   and one `$in` resolves the whole list in a single query.

Category headers (`Pokémon: 17`) are parsed and **discarded**: the category comes from the catalogue.
Trusting the header would import a card as Trainer because the user pasted it in the wrong section.

**Import keeps what it resolves and reports what it does not**, showing the unresolved lines exactly
as written. A list from someone else can name a card from a set we have not synced; refusing all 60
over one line leaves the user with nothing. Verified round-trip: importing the reference list and
exporting it reproduces the input line for line.

**English is the source language.** The repository was bilingual and drifting:
`openSession(id, editar = false)` and `MUESTRA_MINIMA` sat beside `openDeckId` and `played_at`.
Macaronic code is worse than either language pure. `CLAUDE.md` states the project exists to add
full-stack engineering to the developer's career; an English codebase is the industry norm and the
one a reader outside Spain can review. Spanish survives only as a UI translation.

**The interface language is chosen in the client.** Detected from `navigator.language` on the
first visit, then remembered in `localStorage`; an explicit choice always outranks detection. No
backend involvement, no `Accept-Language` negotiation, no user account to store it on.

**A `Violation` carries a code and parameters, never prose.** Rejected: keeping `message` as an
English fallback. Two sources of truth for the same sentence diverge — the Spanish text changes, the
`message` does not, and nobody notices.

**A catalogue string pluralises on exactly one number.** `count` is the reserved parameter that
drives `Intl.PluralRules`; every other number in a string is interpolated as-is, with no plural
selection of its own. A sentence carrying two quantities that vary independently cannot be one
catalogue entry — it has to split into two, each with its own `count`. That is why
`deckStats.played` is two clauses rather than one, and why `deckList.importedCards` and
`importedUnresolved` are two sentences rather than a shared one. Found the hard way: "1 games
across 1 session" rendered with every key resolving and every assertion green — the plural bug was
in the sentence shape, not in any single key.
