<!-- Session handoff. Written 2026-08-29 immediately before a /clear, so the next session can
start without re-deriving any of this. Delete it when the i18n plan is merged. -->

# Start here

## Where the project is

`main` is at the merge of PR #1: the whole repository is English — identifiers, comments,
docstrings, backend strings, interface copy. `grep -rnE "[áéíóúñ¡¿«»]" frontend/src | grep -vE "Pok[eé]"`
returns nothing. Working tree clean, no feature branch open.

## What is NOT done

**The language switch.** `frontend/src/i18n/` does not exist; there is no `useT`, no
`LocaleProvider`, no `navigator.language` anywhere. The app is **English-only**. The developer's
original request was an English/Spanish switch, and the anglicisation was agreed groundwork for
it, not a substitute.

They have chosen to execute the remaining plan.

## What to do

Execute `docs/superpowers/plans/2026-08-28-i18n-locale-switch.md` with
`superpowers:subagent-driven-development`.

**Read that plan's "Execution grouping" section first.** The eleven tasks ship as **six
dispatches** with three review depths, and the section explains why with measured numbers. Do not
dispatch task-by-task; the previous plan did and cost 4.1M subagent tokens.

The three rules that matter most, all earned the hard way:

1. **Never resume an agent to fix a review finding.** Resuming replays its whole transcript — one
   table row cost 241k. Dispatch a fresh cheap agent with only the finding and the file path.
2. **Script the mechanical check before deciding a reviewer is needed.** A multiset comparison of
   quoted literals cost ~2k and proved no UI string moved across eight files.
3. **Commit before writing reports.** Spend limits killed three agents mid-flight; the ones that
   had committed lost only prose.

## Things the plan cannot tell you

- **Shell is zsh with `grep` aliased to `ugrep`.** Quote every `--include`: `--include='*.jsx'`.
  Unquoted, zsh eats it and the command dies with "no matches found". This produced a false
  review finding once.
- **Python is `backend/.venv/bin/python`**, run from the repository root. Frontend checks run
  from `frontend/`.
- **`oxlint` has `no-undef` off.** Lint passing is not evidence that a rename is complete.
- Ports 8000, 8010, 8020 have been used by earlier work; pick a free one. MongoDB runs locally.
- `Pokémon`, `Poké Ball` and `Pokédex` carry acute accents in English — any Spanish-detection
  grep needs `| grep -vE "Pok[eé]"`.
- There is **no test suite** (it is phase 5 of the project). `node:test` ships with Node 24 and
  the i18n plan's first task uses it for the pure translation core — that is the only test
  infrastructure that will exist.

## Two known residues, both deliberate, neither yours to fix silently

- **`"Lista inicial"` / `"Mazo importado"`** are in MongoDB rows written before the rename and
  still render in the deck builder's version list. A one-line `update_many` fixes it; it is the
  developer's call, not a task.
- **`frontend/src/components/DeckList.jsx:300`** calls `setCreating(false)` with no such state
  defined. Real `ReferenceError` on every folder click — it reaches the console rather than
  blocking navigation, because `setCurrentId` runs first and queues the navigation. It predates
  all of this work. Worth fixing, but as its own change, not folded into i18n.

## One open copy decision

`SessionDetail.jsx` uses **"correct"** as a round-level verb where the header uses **"edit"**,
preserving a distinction the Spanish drew (`corregir` / `editar`). Two reviewers noted English
does not lean on "correct" as a casual UI verb. Settle it in the plan's catalogue task, before
the string is frozen into `en.js`.
