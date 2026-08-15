<!-- Reference, not instruction. Deliberately NOT in CLAUDE.md: it is derivable from the
codebase, and CLAUDE.md is loaded into every session whether it is needed or not. -->

# Layout

What is actually there. Four backend layers, and the dependency only ever points downward:
**routers → services → db → models**. A model never imports a router; `pokemon_source.py` stopped
importing `PokemonRef` precisely to keep that true (see the URL decision above).

```
backend/app/
  main.py                  ASGI entrypoint: lifespan, CORS, router registration, index creation
  config.py                settings from .env
  models/       card.py deck.py folder.py match.py pokemon.py session.py stats.py
  routers/      cards.py decks.py folders.py pokemon.py sessions.py
  services/     card_source.py    the only file that knows TCGdex
                card_sync.py      batch job: TCGdex -> mongo, plus the reprint-legality pass
                set_sync.py       batch job: the 188 set abbreviations, for import/export
                deck_rules.py     pure validate_deck(); no I/O, no framework
                deck_text.py      pure parse()/render() of the PTCG Live text format
                pokemon_source.py the only file that knows PokeAPI and its image URLs
                pokemon_sync.py   batch job: PokeAPI -> mongo
  db/           mongo.py          client, lifespan hooks, to_object_id
                card_repository.py deck_repository.py folder_repository.py
                pokemon_repository.py session_repository.py set_repository.py
                stats_repository.py

frontend/src/
  App.jsx                  tabs + which deck/session is open. No router yet: two levels of
                           navigation do not justify the dependency.
  api/          client.js  the only place that calls fetch; turns !response.ok into an exception
                cards.js decks.js folders.js pokemon.js sessions.js
  components/   CardSearch CardDetail
                DeckList DeckScreen DeckBuilder DeckGrid DeckCardList DeckValidation DeckStats
                SessionList SessionDetail
                Menu PokemonPair PokemonPicker TagInput
  App.css index.css        index.css holds the tokens; App.css the components
```

`match.py` is a leftover worth knowing about: it shrank from 130 lines to 47 when sessions took over,
and now only holds the `MatchResult` enum and the BSON date helpers. There is no `matches` collection —
rounds are embedded in the session document.

No `tests/` yet. That is phase 5 and it is honest to say it has not started.
