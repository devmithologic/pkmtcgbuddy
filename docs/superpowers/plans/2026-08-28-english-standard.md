# English Standard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make English the source language of the entire repository — identifiers, comments, docstrings and user-visible strings — without changing a single behaviour.

**Architecture:** No architecture changes. This is a mechanical rewrite, sequenced by *risk* rather than by directory: inert prose first (provably safe), then identifiers (small and reviewable), then user-visible strings (visible but not behavioural). Each group is its own commit so a revert is cheap — this repository has no test suite, and commit granularity is the only safety net there is.

**Tech Stack:** Python 3.12 (`ast` from the standard library, for the verification harness), Node 24, Vite 8, oxlint. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-28-english-standard-and-i18n-design.md`

**Follow-on plan:** `docs/superpowers/plans/2026-08-28-i18n-locale-switch.md` — do not start it until this plan is complete.

## Global Constraints

- **No behaviour changes.** Not a refactor of logic, not a bug fix, not an improvement. If a bug is spotted, write it down and leave it — fixing it inside this diff makes the diff unreviewable.
- **No new dependencies** in `requirements.txt` or `package.json`.
- **Comments keep their job.** Per `CLAUDE.md`, a comment explains the *mechanism and the failure it prevents*, never what the line does. Translate the reasoning; do not summarise it away, and do not add commentary that was not there. A comment that loses its "because X broke" clause has been destroyed, not translated.
- **Never rename anything that crosses the wire.** API field names (`played_at`, `deck_version_id`, `session_type`), enum values (`league`, `cup`, `challenge`, `online`, `testing`, `wrong_size`, `too_many_copies`, …), MongoDB field and collection names, and query parameters are contract. They are already English; leave them exactly as they are.
- **CSS class names are already English.** Do not touch them.
- **Do not translate** card names, set names, format names, or the PTCG Live import/export text format.
- **`SessionList.jsx:20`** — `toLocaleDateString('en-CA')` is not display formatting. It produces `YYYY-MM-DD` for `<input type="date">`. Leave it and keep its comment's explanation.
- **Count paragraphs before you commit.** For every docstring you touch, compare its paragraph
  count against the same docstring at the base commit (`git show <base>:<path>`). The AST harness
  **cannot** catch a lost paragraph — it strips docstrings from both trees by design, so prose is
  exactly its blind spot, and it will keep reporting `0 failures` over a docstring that lost half
  its reasoning. Task 4 dropped one paragraph this way and the harness never noticed; a count
  found it in seconds. Report the audit, not the intention to have done it.
- Every task ends with a commit. Conventional-commit prefix, `refactor:` for prose and identifiers, `feat:`/`fix:` never (nothing changes).

## Glossary

Fixed translations. Consistency across 50 files matters more than the elegance of any single choice — pick from this table, do not improvise, and add a row rather than invent a synonym.

| Spanish | English | Note |
| --- | --- | --- |
| mazo | deck | |
| lista (de mazo) | decklist | the 60 cards; plain `list` when it means a UI list |
| carta | card | |
| impresión | printing | a specific printing of a card |
| sesión | session | |
| ronda | round | |
| partida | game | a single game inside a match; `partidas` in stats = games played |
| rival | opponent | |
| torneo | tournament | |
| carpeta | folder | |
| árbol / padre / hijo | tree / parent / child | |
| camino | path | the breadcrumb trail |
| versión | version | |
| formato | format | Standard / Expanded |
| energía | energy | |
| nombre | name | |
| fecha | date | |
| clave | key | |
| valor | value | |
| campo | field | |
| filtro | filter | |
| orden / ordenar | sort | `order` only for sort direction |
| búsqueda / buscar | search | |
| datos | data | |
| base de datos | database | |
| petición | request | |
| respuesta | response | |
| cliente / servidor | client / server | |
| estado | **state** in React, **status** in HTTP, **state** for a domain condition | disambiguate per site; the most common slip. A third case exists and is not HTTP: the condition of a derived read-model (`DeckValidation`, a sync run) is a *state*. Reserve *status* for HTTP and for a job's discrete lifecycle value. |
| pantalla | screen | |
| botón | button | |
| guardar / borrar / crear / abrir | save / delete / create / open | |

### Identifier renames

Exhaustive. If execution finds one not listed, add it to this table before renaming it.

| Current | New | File |
| --- | --- | --- |
| `_limpia_nombre` | `_clean_name` | `backend/app/db/` (locate with grep) |
| `crearia_ciclo` | `would_create_cycle` | `backend/app/db/folder_repository.py` |
| `camino` | `path` | `frontend/src/components/DeckList.jsx` |
| `carpeta` / `carpetas` | `folder` / `folders` | backend locals, frontend locals |
| `dentro` | `deckCount` | `frontend/src/components/DeckList.jsx` |
| `mazosAqui` | `decksHere` | `frontend/src/components/DeckList.jsx` |
| `MUESTRA_MINIMA` | `MIN_SAMPLE` | `frontend/src/components/DeckStats.jsx` |
| `nombreEditable` | `draftName` | `frontend/src/components/DeckBuilder.jsx` |
| `editar` (param) | `editing` | `frontend/src/App.jsx` |
| `nuevo` (param) | `isNew` | `frontend/src/App.jsx` |
| `carta` / `cartas` | `card` / `cards` | backend locals |
| `clave` | `key` | backend locals |
| `detalle` | `detail` | backend locals |
| `fecha` / `fecha_a` / `fecha_c` | `date` / `date_a` / `date_c` | backend locals — check what `_a`/`_c` mean before renaming |
| `filtro` | `filter_` | backend locals; trailing underscore avoids shadowing the builtin |
| `en_uso` | `in_use` | `backend/app/routers/decks.py` — the 409 guard on deck deletion |

---

## Task 1: Record the convention

Nothing may be translated before the rule that governs it is written down. This is what makes the next thirteen tasks a decision rather than a whim.

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/decisions.md`

**Interfaces:**
- Consumes: nothing
- Produces: the convention every later task cites

- [ ] **Step 1: Replace the language convention in `CLAUDE.md`**

Find this bullet under `## Conventions`:

```markdown
- Code and comments are written in Spanish; `CLAUDE.md` and `log_mentor/` in English. Do not mix
  within a file.
```

Replace it with:

```markdown
- **Everything in this repository is written in English** — identifiers, comments, docstrings,
  documentation and the strings the interface ships with. Spanish exists in exactly one place:
  `frontend/src/i18n/es.js`, as a translation of the interface. Conversation with the developer
  stays in Spanish; the artifact does not.
```

- [ ] **Step 2: Add the decision rows to `docs/decisions.md`**

Append three entries in the file's existing style (read a neighbouring entry first and match its shape — heading, the decision, then the reasoning and what was rejected):

1. **English is the source language.** The repository was bilingual and drifting: `openSession(id, editar = false)` and `MUESTRA_MINIMA` sat beside `openDeckId` and `played_at`. Macaronic code is worse than either language pure. `CLAUDE.md` states the project exists to add full-stack engineering to the developer's career; an English codebase is the industry norm and the one a reader outside Spain can review. Spanish survives only as a UI translation.
2. **The interface language is chosen in the client.** Detected from `navigator.language` on the first visit, then remembered in `localStorage`; an explicit choice always outranks detection. No backend involvement, no `Accept-Language` negotiation, no user account to store it on.
3. **A `Violation` carries a code and parameters, never prose.** Rejected: keeping `message` as an English fallback. Two sources of truth for the same sentence diverge — the Spanish text changes, the `message` does not, and nobody notices.

- [ ] **Step 3: Add the index rows to the `CLAUDE.md` decision table**

The table under "Before you act: read the decision record" is the index. Add one row per decision, in the existing `| Decision | Why, in short |` format:

```markdown
| English is the source language of the repo | a bilingual codebase drifts; the artifact is a portfolio |
| The UI language is detected, then remembered | `navigator.language` once, then `localStorage` wins |
| A `Violation` carries a code and params, not prose | prose plus a code is two sources of truth |
```

- [ ] **Step 4: Verify**

Run: `grep -n "Spanish" CLAUDE.md`
Expected: only the new bullet mentions Spanish, and it mentions it as the translation target. No stale rule survives.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md docs/decisions.md
git commit -m "docs: make English the source language of the repository"
```

---

## Task 2: Build the AST-equality harness

The claim "I only touched comments" is worth nothing unasserted. This harness turns it into a proof, and it must exist before the first line is translated.

**Files:**
- Create: `/private/tmp/claude-501/-Users-mithologic-ws-dev-pkmtrainerproject/15dded0c-e036-4ced-8e69-a9321da5f1f2/scratchpad/verify_ast_equality.py` — **not committed.** It is a verification tool for this refactor, not a project asset; committing it would leave permanent cruft for a one-off job.

**Interfaces:**
- Consumes: nothing
- Produces: `python /private/tmp/claude-501/-Users-mithologic-ws-dev-pkmtrainerproject/15dded0c-e036-4ced-8e69-a9321da5f1f2/scratchpad/verify_ast_equality.py <git-ref>`, exit 0 when every tracked `backend/app/**/*.py` has an identical AST in the working tree and in `<git-ref>`, ignoring docstrings and comments. Tasks 3–6 each end by running it.

- [ ] **Step 1: Write the harness**

```python
"""Prove that a change touched only comments and docstrings.

Comments never reach Python's AST at all, so they are free. Docstrings do reach
it — they are ordinary string expressions — so they are stripped from both trees
before comparing. What is left is every statement the interpreter will run.

`ast.dump` is called with the default `include_attributes=False`, and that default
is the whole trick: line and column numbers stay out of the dump, so a docstring
that grows from three lines to five shifts nothing.
"""

import ast
import subprocess
import sys
from pathlib import Path

TARGET = "backend/app"

DOCSTRING_OWNERS = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def strip_docstrings(tree: ast.AST) -> ast.AST:
    """Remove every docstring node, in place, from a parsed tree."""
    for node in ast.walk(tree):
        if not isinstance(node, DOCSTRING_OWNERS):
            continue
        body = node.body
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            # `or [ast.Pass()]` because a body cannot be empty: a function whose
            # only content was a docstring would otherwise produce invalid AST.
            node.body = body[1:] or [ast.Pass()]
    return tree


def fingerprint(source: str) -> str:
    return ast.dump(strip_docstrings(ast.parse(source)))


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", TARGET],
        capture_output=True, text=True, check=True,
    ).stdout
    return [p for p in out.splitlines() if p.endswith(".py")]


def main(ref: str) -> int:
    paths = tracked_files()
    failures = []
    for path in paths:
        before = subprocess.run(
            ["git", "show", f"{ref}:{path}"],
            capture_output=True, text=True, check=True,
        ).stdout
        after = Path(path).read_text(encoding="utf-8")
        try:
            same = fingerprint(before) == fingerprint(after)
        except SyntaxError as exc:
            failures.append(f"{path}: does not parse — {exc}")
            continue
        if not same:
            failures.append(f"{path}: AST differs — a statement changed, not just prose")

    for line in failures:
        print(line)
    print(f"\n{len(paths) - len(failures)} file(s) provably prose-only, "
          f"{len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "HEAD"))
```

- [ ] **Step 2: Prove the harness passes on an unchanged tree**

Run: `cd /Users/mithologic/ws/dev/pkmtrainerproject && backend/.venv/bin/python /private/tmp/claude-501/-Users-mithologic-ws-dev-pkmtrainerproject/15dded0c-e036-4ced-8e69-a9321da5f1f2/scratchpad/verify_ast_equality.py HEAD`
Expected: `0 failure(s)`, exit 0. A clean tree must compare equal to itself.

- [ ] **Step 3: Prove the harness actually catches something**

A verification tool that has never failed is not known to work. Break something on purpose:

```bash
# pick any file and change a real statement
sed -i '' 's/^DECK_SIZE = 60$/DECK_SIZE = 61/' backend/app/models/deck.py
backend/.venv/bin/python /private/tmp/claude-501/-Users-mithologic-ws-dev-pkmtrainerproject/15dded0c-e036-4ced-8e69-a9321da5f1f2/scratchpad/verify_ast_equality.py HEAD
```

Expected: `backend/app/models/deck.py: AST differs`, exit 1.

- [ ] **Step 4: Prove it ignores a docstring rewrite**

```bash
git checkout backend/app/models/deck.py
# now change only prose: translate one docstring line by hand
```

Run the harness again.
Expected: `0 failure(s)`. This is the behaviour tasks 3–6 depend on.

- [ ] **Step 5: Restore the tree**

```bash
git checkout backend/app/models/deck.py
git status --porcelain   # expected: empty
```

No commit — nothing in the repository changed.

---

## Task 3: Translate `backend/app/models/` prose

**Files:**
- Modify: `backend/app/models/__init__.py`, `card.py`, `deck.py`, `folder.py`, `match.py`, `pokemon.py`, `session.py`, `stats.py`

**Interfaces:**
- Consumes: the glossary; the harness from Task 2
- Produces: nothing new — this is prose only

- [ ] **Step 1: Translate every comment and docstring in the eight files**

Follow the glossary. Preserve each comment's structure: if it names a bug that bit the project, the English must still name that bug. `deck.py` carries the `ViolationCode` docstring that explains why a code travels beside the message — that reasoning is about to be cashed in by the i18n plan, so translate it precisely.

Do not touch: enum values, field names, `Field(...)` arguments, `@computed_field` names, or any string that is data.

- [ ] **Step 2: Prove no statement changed**

Run: `backend/.venv/bin/python /private/tmp/claude-501/-Users-mithologic-ws-dev-pkmtrainerproject/15dded0c-e036-4ced-8e69-a9321da5f1f2/scratchpad/verify_ast_equality.py HEAD`
Expected: `0 failure(s)`, exit 0.

- [ ] **Step 3: Prove the app still imports**

Run: `cd backend && .venv/bin/python -c "import app.main"`
Expected: no output, exit 0.

- [ ] **Step 4: Check nothing Spanish survived**

Run: `grep -rnE "[áéíóúñ¡¿«»]" backend/app/models/ | grep -vE "Pok[eé]"`
Expected: no output.

The `| grep -vE "Pok[eé]"` is not a fudge. `Pokémon`, `Pokédex` and `Poké Ball` are all spelled with an acute accent in English too, so an accent-based Spanish detector reports every one of them as a false positive. The pattern covers the family rather than the one word, because Task 5 found `Poké Ball` and `Pokédex` that an earlier `Pokémon`-only filter let through as apparent misses. Every other hit is a real miss and must be justified out loud, not ignored.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/
git commit -m "refactor: translate model comments and docstrings to English"
```

---

## Task 4: Translate `backend/app/db/` prose

The heaviest prose in the repository lives here — `card_repository.py` alone carries 125 accented lines, and much of it is the reasoning behind index choices and the substring-search decision.

**Files:**
- Modify: `backend/app/db/__init__.py`, `card_repository.py`, `deck_repository.py`, `folder_repository.py`, `mongo.py`, `pokemon_repository.py`, `session_repository.py`, `set_repository.py`, `stats_repository.py`

**Interfaces:**
- Consumes: the glossary; the harness from Task 2
- Produces: nothing new

- [ ] **Step 1: Translate every comment and docstring in the nine files**

Watch for three things specific to this directory:

- Comments that quote a **measurement** ("measured at 1 successful request in 10", "the whole `sve` set has no image"). The number and the claim must survive intact; they are the evidence behind a decision in `docs/decisions.md`.
- Mongo **aggregation pipeline** comments, where `estado` almost always means *stage state*, not React state.
- **Index** commentary. `orden` here is usually sort direction, not sorting in general — use `order`.

Do not touch: collection names, field names inside `$match`/`$project`/`$sort` documents, index names.

- [ ] **Step 2: Prove no statement changed**

Run: `backend/.venv/bin/python /private/tmp/claude-501/-Users-mithologic-ws-dev-pkmtrainerproject/15dded0c-e036-4ced-8e69-a9321da5f1f2/scratchpad/verify_ast_equality.py HEAD`
Expected: `0 failure(s)`, exit 0.

- [ ] **Step 3: Prove the app still imports**

Run: `cd backend && .venv/bin/python -c "import app.main"`
Expected: no output, exit 0.

- [ ] **Step 4: Check nothing Spanish survived**

Run: `grep -rnE "[áéíóúñ¡¿«»]" backend/app/db/ | grep -vE "Pok[eé]"`
Expected: no output. `Pokémon` is filtered because it carries an acute accent in English too.

- [ ] **Step 5: Commit**

```bash
git add backend/app/db/
git commit -m "refactor: translate repository comments and docstrings to English"
```

---

## Task 5: Translate `backend/app/services/` prose

**Files:**
- Modify: `backend/app/services/__init__.py`, `card_source.py`, `card_sync.py`, `deck_rules.py`, `deck_text.py`, `pokemon_source.py`, `pokemon_sync.py`, `set_sync.py`

**Interfaces:**
- Consumes: the glossary; the harness from Task 2
- Produces: nothing new

- [ ] **Step 1: Translate every comment and docstring in the eight files**

Specific hazards here:

- `deck_rules.py` opens with a numbered list of the deck-construction rules and an explicit note about the Radiant Pokémon limit **not** being implemented. That "not implemented, and worth knowing" note is the most valuable comment in the file — it must survive as such, not be softened.
- `card_source.py` and `pokemon_source.py` are the adapters. Their comments explain the containment decision (every external call behind one adapter). Keep the reasoning.
- `deck_text.py` handles the PTCG Live format. Its comments will mention example lines like `3 Riolu PRE 50` — those are **format samples, not prose**. Leave them byte-for-byte.

- [ ] **Step 2: Prove no statement changed**

Run: `backend/.venv/bin/python /private/tmp/claude-501/-Users-mithologic-ws-dev-pkmtrainerproject/15dded0c-e036-4ced-8e69-a9321da5f1f2/scratchpad/verify_ast_equality.py HEAD`
Expected: `0 failure(s)`, exit 0.

- [ ] **Step 3: Prove the app still imports**

Run: `cd backend && .venv/bin/python -c "import app.main"`
Expected: no output, exit 0.

- [ ] **Step 4: Check what Spanish survived, and why**

Run: `grep -rnE "[áéíóúñ¡¿«»]" backend/app/services/ | grep -vE "Pok[eé]"`

Expected: **only string literals**, never a comment or a docstring. There are roughly fifty of
them in this directory and every one belongs to Task 8, not to you:

- `deck_rules.py` — five `message=` strings (not three; an earlier draft of this plan
  undercounted, and the ACE SPEC and format-legality messages were missed).
- `card_sync.py`, `pokemon_sync.py`, `set_sync.py` — the progress and summary lines these batch
  jobs print to a terminal, plus their `argparse` help text.
- `card_source.py`, `pokemon_source.py` — `RuntimeError` and `ValueError` messages raised when a
  provider answers with something unexpected.

They are output, not prose, and they live in the AST — translating one here makes Step 2 fail,
correctly. Verify each surviving hit is one of the above. A surviving **comment** is a miss.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/
git commit -m "refactor: translate service comments and docstrings to English"
```

---

## Task 6: Translate `backend/app/routers/`, the app root, and `requirements.txt`

**Files:**
- Modify: `backend/app/routers/__init__.py`, `cards.py`, `decks.py`, `folders.py`, `pokemon.py`, `sessions.py`
- Modify: `backend/app/__init__.py`, `backend/app/config.py`, `backend/app/main.py`
- Modify: `backend/requirements.txt`
- Modify: `backend/.env.example`

**Interfaces:**
- Consumes: the glossary; the harness from Task 2
- Produces: nothing new

- [ ] **Step 1: Translate the router and root prose**

`main.py` carries the lifespan and CORS commentary — both are documented lessons in `log_mentor/` and the comments must keep pointing at the same mechanism. Do not touch route paths, `response_model=`, status codes, or the `detail=` strings (Task 8).

**Leave every `Query(...)` and `Path(...)` `description=` alone.** They read like prose but they
are arguments, so they live in the AST — translating one here makes Step 3's equality check fail,
correctly. They are user-facing API documentation and Task 8 owns them. There are six, and an
earlier draft of this plan named only the last:

```
backend/app/routers/cards.py:28     "Parte del nombre"
backend/app/routers/cards.py:29     "Filtra por legalidad"
backend/app/routers/cards.py:31     "Solo cartas ACE SPEC"
backend/app/routers/pokemon.py:18   "Parte del nombre"
backend/app/routers/sessions.py:89  "Filtra por etiqueta"
backend/app/routers/decks.py:403    "Filtra por etiqueta de sesión"
```

Likewise leave every `detail=` string, every `HTTPException` message, and the two strings that
are written into MongoDB (`decks.py:204` `"Mazo importado"`). All of them are Task 8's.

- [ ] **Step 2: Translate the `requirements.txt` and `.env.example` comments**

`requirements.txt` currently opens with a Spanish note about lower bounds versus pinned versions, and every dependency carries a Spanish trailing comment. Translate both. Do not change a single version specifier.

- [ ] **Step 3: Prove no statement changed**

Run: `backend/.venv/bin/python /private/tmp/claude-501/-Users-mithologic-ws-dev-pkmtrainerproject/15dded0c-e036-4ced-8e69-a9321da5f1f2/scratchpad/verify_ast_equality.py HEAD`
Expected: `0 failure(s)`, exit 0.

- [ ] **Step 4: Prove `requirements.txt` still resolves**

Run: `cd backend && .venv/bin/python -m pip install --dry-run -r requirements.txt`
Expected: resolves without error. This catches a comment marker accidentally eaten on a dependency line.

- [ ] **Step 5: Start the API and hit one endpoint per router**

```bash
cd backend && .venv/bin/uvicorn app.main:app --port 8000 &
sleep 3
curl -sf localhost:8000/api/decks   > /dev/null && echo "decks ok"
curl -sf localhost:8000/api/sessions > /dev/null && echo "sessions ok"
curl -sf "localhost:8000/api/cards?q=iono" > /dev/null && echo "cards ok"
curl -sf localhost:8000/api/folders  > /dev/null && echo "folders ok"
curl -sf "localhost:8000/api/pokemon?q=pikachu" > /dev/null && echo "pokemon ok"
```

Expected: five `ok` lines. Check the exact paths and query parameters against `docs/api.md` before running — that file is the contract, this snippet is from memory.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/ backend/app/__init__.py backend/app/config.py backend/app/main.py backend/requirements.txt backend/.env.example
git commit -m "refactor: translate router, app root and dependency comments to English"
```

---

## Task 7: Rename Spanish identifiers in the backend

The first task in this plan that can actually break something. It is deliberately small, and deliberately separate from Tasks 3–6 so that a bisect lands on it immediately.

**Files:**
- Modify: whichever `backend/app/**/*.py` the grep in Step 1 reports

**Interfaces:**
- Consumes: the identifier table in the Glossary section
- Produces: the same public API under English local names. **No exported name changes** — `_limpia_nombre` and `crearia_ciclo` are module-private (leading underscore or single-module use); confirm that with grep before renaming, and if either is imported elsewhere, rename every call site in the same commit.

- [ ] **Step 1: Enumerate every Spanish identifier**

```bash
cd backend
grep -rnoE "\b(def|class) +[a-zA-Z_]+" --include='*.py' app | sort -u
grep -rnoE "^[[:space:]]*[a-z_]+ *=" --include='*.py' app | tr -d ' =' | sort -u
grep -rnoE "\bfor +[a-z_, ]+ in\b" --include='*.py' app | sort -u
```

Read the three lists. Every Spanish name found must either appear in the identifier table or be added to it. Do not rename anything not in the table.

- [ ] **Step 2: Confirm the two function renames are module-private**

```bash
grep -rn "_limpia_nombre\|crearia_ciclo" --include='*.py' app
```

Expected: every hit is in the same file as the definition. If not, the rename must include the importing module, in this same commit.

- [ ] **Step 3: Rename, one name at a time**

For each row in the identifier table, rename with an exact word-boundary match and re-grep to confirm zero survivors:

```bash
grep -rn "\bcrearia_ciclo\b" --include='*.py' app   # see every site first
# apply the rename
grep -rn "\bcrearia_ciclo\b" --include='*.py' app   # expected: no output
```

Do **not** use a blanket `sed` across the tree. `carta` is a substring of nothing dangerous, but `clave` appears inside `clave_reimpresion`-style compounds and `orden` inside `ordenar`; a bare substring replace corrupts them.

- [ ] **Step 4: The AST harness must now FAIL — read the failure**

Find the baseline — the commit from Task 1, before any Python was touched — rather than counting
back a fixed number of commits:

```bash
BASE=$(git log --format='%H %s' | grep 'make English the source language' | head -1 | cut -d' ' -f1)
backend/.venv/bin/python /private/tmp/claude-501/-Users-mithologic-ws-dev-pkmtrainerproject/15dded0c-e036-4ced-8e69-a9321da5f1f2/scratchpad/verify_ast_equality.py "$BASE"
```

Expected: failures, because identifiers *are* part of the AST. This is correct. The harness's job is finished; from here verification is by import, lint and smoke test. Note which files it names and confirm each one is a file you intended to touch — a file you did not intend to rename in, showing up here, is a real finding.

- [ ] **Step 5: Prove the app imports and answers**

```bash
cd backend && .venv/bin/python -c "import app.main"
.venv/bin/uvicorn app.main:app --port 8000 &
sleep 3
curl -sf localhost:8000/api/folders > /dev/null && echo "folders ok"
curl -sf localhost:8000/api/decks   > /dev/null && echo "decks ok"
```

Expected: both `ok`. The folder endpoint matters most — `crearia_ciclo` is the cycle guard in `folder_repository.py`, and a half-applied rename there raises `NameError` only on the path that moves a folder.

- [ ] **Step 6: Exercise the renamed cycle guard specifically**

Create two folders, then try to make the parent a child of its own child. Use `docs/api.md` for the exact endpoint and payload shape.
Expected: a 400 or 409 with the cycle error, not a 500 with `NameError`.

- [ ] **Step 7: Commit**

```bash
git add backend/app/
git commit -m "refactor: rename Spanish identifiers in the backend"
```

---

## Task 8: Translate every Spanish string literal in the backend

The only backend task that changes what anyone reads. Separate from Task 7 so the diff answers
exactly one question.

**Scope correction.** An earlier draft of this plan scoped this task at "three violation messages
and seven `detail=` strings". An AST walk of the whole backend found **about sixty** Spanish
string literals outside docstrings. `routers/folders.py` was missing from the file list entirely,
`deck_rules.py` has five messages rather than three, and the three sync jobs print roughly thirty
Spanish lines to a terminal that nothing in the plan accounted for.

**Files:**
- Modify: `backend/app/services/deck_rules.py` — five `message=` strings
- Modify: `backend/app/services/card_sync.py`, `pokemon_sync.py`, `set_sync.py` — progress output and `argparse` help
- Modify: `backend/app/services/card_source.py`, `pokemon_source.py` — raised-exception messages
- Modify: `backend/app/db/mongo.py` — one `RuntimeError` message
- Modify: `backend/app/db/deck_repository.py` — `"Lista inicial"` (see the stored-data warning)
- Modify: `backend/app/routers/cards.py`, `decks.py`, `folders.py`, `sessions.py`, `pokemon.py`
- Modify: `docs/api.md` if it quotes any of these strings verbatim

**Interfaces:**
- Consumes: nothing
- Produces: English `message`, `detail`, `description` and console strings. The i18n plan later
  replaces `message` entirely with `code` + `params` — do **not** anticipate that here.
  Translating first and restructuring second keeps the two diffs answerable.

### Two strings are written into MongoDB

`deck_repository.py:125` `"Lista inicial"` and `routers/decks.py:204` `"Mazo importado"` are not
displayed constants — they are stored as the `message` of a `DeckVersion` at the moment it is
created, and the deck builder's version list renders them back.

Translate them. But understand what that does: **rows already in the database keep the Spanish
text.** New versions will read "Initial list", older ones will still read "Lista inicial", and no
code change fixes that. A one-line `update_many` would, and it is deliberately **out of scope** —
this plan does not mutate the user's data. Note it in your report so it reaches the developer as
a choice rather than as a surprise.

- [ ] **Step 1: Regenerate the exact inventory**

Do not work from the lists below alone — they were correct when written and the tree has moved
since. Enumerate first:

```bash
backend/.venv/bin/python - <<'EOF'
import ast, pathlib, re, subprocess
SPANISH = re.compile(r"[áéíóúñ¿¡«»]|\b(el|la|los|las|un|una|de|del|que|no|se|es|por|para|con|sin|hay|carta|cartas|mazo|mazos|sesion|carpeta|nombre|lista|inicial|nuevo|nueva|existe|filtra|parte|solo|etiqueta|ronda|rondas)\b", re.I)
for path in sorted(p for p in subprocess.run(["git","ls-files","backend/app"],capture_output=True,text=True).stdout.split() if p.endswith(".py")):
    tree = ast.parse(pathlib.Path(path).read_text())
    docs = set()
    for n in ast.walk(tree):
        if isinstance(n,(ast.Module,ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)) and n.body:
            f = n.body[0]
            if isinstance(f,ast.Expr) and isinstance(f.value,ast.Constant) and isinstance(f.value.value,str):
                docs.add(id(f.value))
    for n in ast.walk(tree):
        if isinstance(n,ast.Constant) and isinstance(n.value,str) and id(n) not in docs \
           and len(n.value) > 3 and SPANISH.search(n.value):
            print(f"{path}:{n.lineno}  {n.value[:70]!r}")
EOF
```

The word `version` is an English false positive of that regex — ignore those rows. `"Pokémon"` in
`deck_text.py` is the PTCG Live format's own section header and must not change.

- [ ] **Step 2: Translate the five violation messages**

```python
message=f"{len(unknown)} card(s) are not in the synced catalogue"
message=f"A deck is {DECK_SIZE} cards: there are {total}, {detail}"
message=f'"{name}": {n} copies, the maximum is {MAX_COPIES_PER_NAME}'
message=f"{ace_total} ACE SPEC cards: only {MAX_ACE_SPEC} is allowed per deck"
message=f"{len(illegal)} card(s) are not legal in {deck_format.value}: {sample}"
```

Note the quote change on the third: the Spanish used `«…»`, a Spanish typographic convention.
English uses `"…"`, so the f-string's outer delimiter becomes `'` as shown.

The `detail` local interpolated into the second message is itself Spanish prose built two lines
above (`faltan {n}` / `sobran {n}`). Translate it too, or the sentence stays half-Spanish.

- [ ] **Step 3: Translate the router strings**

Three kinds, all in `routers/`:

1. **`detail=` on `HTTPException`** — about fourteen, across `cards.py`, `decks.py`, `folders.py`
   and `sessions.py`. `folders.py` has `"Esa carpeta no existe"` twice and the cycle guard's
   `"Una carpeta no puede moverse dentro de sí misma ni de una de sus subcarpetas"`.
2. **`Query(description=...)`** — six, listed in Task 6. They are OpenAPI documentation and show
   up in `/docs`.
3. **Two that no `grep detail=` will find:**
   - `decks.py:311` — the 409 refusing to delete a deck that sessions used. Raised
     **positionally**, and it carries a hand-rolled plural
     (`'sesión se jugó' if en_uso == 1 else 'sesiones se jugaron'` — by now `in_use`, renamed in
     Task 7). Both branches must become whole English clauses, never a stem plus a suffix.
   - `decks.py:166` and `:195` — the import failures, which quote the PTCG Live line format
     `«3 Riolu PRE 50»`. Translate the sentence around it; leave the example line exactly as it
     is, and switch the Spanish quotation marks to English ones.

- [ ] **Step 4: Translate the console output of the three sync jobs**

`card_sync.py`, `pokemon_sync.py` and `set_sync.py` print progress and a summary to a terminal,
and expose `argparse` help. About thirty strings. They are developer-facing, not user-facing, but
they are Spanish in an English repository.

Preserve every `·` separator, every unit, and every alignment space — these lines are formatted
to line up in a terminal, and an English word of a different length can break a column. Check the
f-string placeholders survive: `{...}` counts must match before and after.

`card_sync.py:278` (`La colección \`sets\` está vacía. Ejecuta antes:`) and `cards.py:57`
(`No hay cartas sincronizadas. Ejecuta: python -m app.services.card_sync`) both tell the reader a
command to run. Translate the sentence; leave the command verbatim.

- [ ] **Step 5: Translate the raised-exception messages**

`db/mongo.py:40`, `services/card_source.py` (five) and `services/pokemon_source.py` (one). These
are internal invariants — "MongoDB is not connected: did the app's lifespan run?" — and they are
read by whoever is debugging. Keep the question form where the Spanish used one; it is doing
work, pointing at the likely cause.

- [ ] **Step 6: Translate the two stored-data strings**

`deck_repository.py:125` and `routers/decks.py:204`, per the warning above. Do **not** write a
migration.

- [ ] **Step 7: Confirm no Spanish remains anywhere in the backend**

Run: `grep -rnE "[áéíóúñ¡¿«»]" backend/app backend/requirements.txt backend/.env.example | grep -vE "Pok[eé]"`
Expected: no output.

Then re-run the AST inventory from Step 1. Expected: only rows whose text is the English word
`version`, and `deck_text.py`'s `"Pokémon"`.

- [ ] **Step 8: Prove the app still runs, and read the new strings**

```bash
cd backend && .venv/bin/python -c "import app.main"
.venv/bin/uvicorn app.main:app --port 8000 &
sleep 3
curl -s localhost:8000/api/decks/000000000000000000000000 | head -c 200
curl -s "localhost:8000/openapi.json" | grep -o "Part of the name" | head -1
```

Expected: an English `detail` on the 404, and the translated `Query` description present in the
OpenAPI document.

Then provoke a violation: build or edit a deck with five copies of one non-energy card and fetch
its validation. Expected: `"Iono": 5 copies, the maximum is 4` — English, straight quotes,
correct numbers.

- [ ] **Step 9: Commit, in two commits**

The two halves have different audiences and different blast radius. Keep them apart so a reviewer
can reject one without the other:

```bash
git add backend/app/routers/ backend/app/services/deck_rules.py backend/app/db/deck_repository.py docs/api.md
git commit -m "refactor: translate the backend's HTTP-facing strings to English"

git add backend/app/services/ backend/app/db/mongo.py
git commit -m "refactor: translate sync output and internal exceptions to English"
```

---

## Task 9: Translate `frontend/src/api/`, `main.jsx` and `sessionTypes.js` prose

The frontend has no AST harness. From here, verification is lint, build, and eyes.

**Files:**
- Modify: `frontend/src/api/cards.js`, `client.js`, `decks.js`, `folders.js`, `pokemon.js`, `sessions.js`
- Modify: `frontend/src/main.jsx`, `frontend/src/sessionTypes.js`

**Interfaces:**
- Consumes: the glossary
- Produces: nothing new

- [ ] **Step 1: Translate the comments in the eight files**

`client.js` carries the error-shape handling — the comment explaining that a 422 `detail` is an array of `{loc, msg, type}` is load-bearing knowledge, keep it precise. `sessionTypes.js` opens with the Vite fast-refresh explanation (a module that exports both components and constants forces a full reload); that reasoning is why the file exists at all.

- [ ] **Step 2: Do not touch the `SESSION_TYPES` values or labels**

`value` is contract with the backend enum. `label` is user-visible text and belongs to Task 13. This task changes comments only.

- [ ] **Step 3: Lint and build**

```bash
cd frontend && npm run lint && npm run build
```
Expected: both pass.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/ frontend/src/main.jsx frontend/src/sessionTypes.js
git commit -m "refactor: translate API client comments to English"
```

---

## Task 10: Translate the five largest components' prose

Split from Task 11 purely by size: these five carry the densest reasoning, and a reviewer should be able to read one commit in a sitting.

**Files:**
- Modify: `frontend/src/components/DeckBuilder.jsx`, `DeckList.jsx`, `SessionDetail.jsx`, `CardSearch.jsx`, `DeckStats.jsx`

**Interfaces:**
- Consumes: the glossary
- Produces: nothing new

- [ ] **Step 1: Translate every comment in the five files**

Comments to handle with particular care, because each records a bug that was actually hit:

- `DeckBuilder.jsx` — why the 60-card counter was moved (it fell off-screen exactly when there were unsaved changes).
- `DeckList.jsx` — why deck rows reserve icon width (decks with no Pokémon started their name 130 px earlier and the list looked broken).
- `CardSearch.jsx` — the debounce and the out-of-order response guard.
- `DeckStats.jsx` — why rows below the minimum sample are dimmed.

Translate the causes, not just the conclusions.

- [ ] **Step 2: Leave every user-visible string in Spanish for now**

This task changes comments only. Mixing string changes in makes the diff impossible to skim.

- [ ] **Step 3: Lint and build**

```bash
cd frontend && npm run lint && npm run build
```
Expected: both pass.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/DeckBuilder.jsx frontend/src/components/DeckList.jsx frontend/src/components/SessionDetail.jsx frontend/src/components/CardSearch.jsx frontend/src/components/DeckStats.jsx
git commit -m "refactor: translate comments in the main deck and session components"
```

---

## Task 11: Translate the remaining components and the stylesheets

**Files:**
- Modify: `frontend/src/App.jsx`, `frontend/src/components/CardDetail.jsx`, `DeckCardList.jsx`, `DeckGrid.jsx`, `DeckScreen.jsx`, `DeckValidation.jsx`, `Menu.jsx`, `PokemonPair.jsx`, `PokemonPicker.jsx`, `SessionList.jsx`, `TagInput.jsx`
- Modify: `frontend/src/App.css`, `frontend/src/index.css`

**Interfaces:**
- Consumes: the glossary
- Produces: nothing new

- [ ] **Step 1: Translate the component comments**

Three carry decisions recorded in `docs/decisions.md` — keep them recognisable as the same decision:

- `Menu.jsx` — one `Menu` for every popover, and the only `document` listener in the app.
- `DeckValidation.jsx` — why unsaved changes replace the verdict with "unchecked" instead of recomputing the rules client-side.
- `App.jsx` — why the hidden tab is unmounted rather than hidden with CSS (it cancels in-flight requests through `useEffect` cleanups).

- [ ] **Step 2: Leave every user-visible string in Spanish for now**

Comments only, exactly as in Task 10. The interface copy is Task 13, and mixing the two makes
the diff impossible to skim.

- [ ] **Step 3: Translate the CSS comments**

`App.css` has 95 accented lines and `index.css` 25. Class names are already English and must not change — only comments. `App.css` documents the `--shell` and `--measure` width decision; keep it precise, it is a row in the decision table.

- [ ] **Step 4: Confirm no class name moved**

```bash
git diff -- frontend/src/App.css frontend/src/index.css | grep -E "^[-+]\s*\." | sort | uniq -c
```
Expected: every removed selector line has a matching added line, or no selector lines appear at all. A selector that appears only on a `-` line is a renamed class and a bug.

- [ ] **Step 5: Lint and build**

```bash
cd frontend && npm run lint && npm run build
```
Expected: both pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/App.jsx frontend/src/components/ frontend/src/App.css frontend/src/index.css
git commit -m "refactor: translate remaining component and stylesheet comments to English"
```

---

## Task 12: Rename Spanish identifiers in the frontend

**Files:**
- Modify: `frontend/src/App.jsx`, `frontend/src/components/DeckList.jsx`, `DeckStats.jsx`, `DeckBuilder.jsx`, and any file the grep in Step 1 adds

**Interfaces:**
- Consumes: the identifier table in the Glossary section
- Produces: `App.jsx` exposes `openSession(id, editing = false)` and `onOpen(id, isNew = false)`. These are **positional** parameters — renaming them changes no call site, but the props they feed (`startEditing`, `isNew`) already exist and must not be renamed.

- [ ] **Step 1: Enumerate**

```bash
cd frontend/src
grep -rnoE "\b(const|let|var|function) +[a-zA-Z_$]+" . | awk '{print $2}' | sort -u
```

Read the list. Every Spanish name must be in the identifier table or added to it.

- [ ] **Step 2: Rename one name at a time, with word boundaries**

```bash
grep -rn "\bMUESTRA_MINIMA\b" .    # every site
# apply
grep -rn "\bMUESTRA_MINIMA\b" .    # expected: no output
```

`camino` is the riskiest: it is the breadcrumb trail in `DeckList.jsx` and appears in a ternary that renders the current folder name (`camino.length ? camino[camino.length - 1].name : 'Mazos'`). Verify that line by eye after the rename.

- [ ] **Step 3: Lint and build**

```bash
cd frontend && npm run lint && npm run build
```
Expected: both pass. oxlint reports undefined identifiers, which is exactly the failure a half-applied rename produces.

- [ ] **Step 4: Smoke-test the three affected screens**

Start the app, then:
- **Decks list** — navigate into a folder and back out. The breadcrumb must show the folder path (`camino` → `path`).
- **Decks list** — a folder row must show its deck count (`dentro` → `deckCount`).
- **Deck stats** — open a deck's stats; rows under the minimum sample must still be dimmed (`MUESTRA_MINIMA` → `MIN_SAMPLE`).
- **Deck builder** — rename a deck; the draft name must still be editable (`nombreEditable` → `draftName`).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/
git commit -m "refactor: rename Spanish identifiers in the frontend"
```

---

## Task 13: Translate the interface strings, and fix the two broken plurals

The task that makes the change visible. At the end of it the application is English-only; Spanish returns in the i18n plan.

**Files:**
- Modify: `frontend/src/App.jsx` (the `TABS` labels), `frontend/src/sessionTypes.js` (the `SESSION_TYPES` labels), and all 15 components

**Interfaces:**
- Consumes: the glossary
- Produces: English UI copy that the i18n plan will lift into `frontend/src/i18n/en.js` verbatim. Write the copy well now — it becomes the source catalogue, and rewording it later means rewording the Spanish too.

- [ ] **Step 1: Translate `TABS` and `SESSION_TYPES` labels**

```jsx
// App.jsx
const TABS = [
  { id: 'sessions', label: 'Sessions' },
  { id: 'decks', label: 'Decks' },
  { id: 'cards', label: 'Cards' },
]
```

```js
// sessionTypes.js — values are contract with the backend enum; only labels change
export const SESSION_TYPES = [
  { value: 'league', label: 'League' },
  { value: 'cup', label: 'Cup' },
  { value: 'challenge', label: 'Challenge' },
  { value: 'online', label: 'Online' },
  { value: 'testing', label: 'Testing' },
]
```

- [ ] **Step 2: Fix the two hand-rolled plurals before translating them**

Both split a word and glue a suffix. That does not survive translation, because English does not form plurals at the same seam.

```jsx
// DeckList.jsx — was: `${dentro} ${dentro === 1 ? 'mazo' : 'mazos'}`
`${deckCount} ${deckCount === 1 ? 'deck' : 'decks'}`
```

```jsx
// DeckStats.jsx — was: sesion + {n === 1 ? '' : 'es'}
{overall.played} games across {stats.sessions_counted}{' '}
{stats.sessions_counted === 1 ? 'session' : 'sessions'}
```

Whole words on both branches. The i18n plan turns each into a `{ one, other }` catalogue entry; leaving them split would make that impossible.

- [ ] **Step 3: Translate every remaining string in the 15 components**

Includes: headings, button labels, form labels, `placeholder` attributes, `aria-label` attributes, empty states, confirmation copy, and the explanatory paragraphs in `DeckStats.jsx` and `DeckList.jsx`.

Leave untouched, per the Global Constraints: `SESSION_TYPES[].value`, `toLocaleDateString('en-CA')` in `SessionList.jsx:20`, the PTCG Live placeholder in `DeckList.jsx:513` (`'Pokémon: 17\n3 Riolu PRE 50\n…'` — that is the interop format, and it is already English), and card/set/format names.

- [ ] **Step 4: Confirm no Spanish remains in the frontend**

Run: `grep -rnE "[áéíóúñ¡¿«»]" frontend/src/ | grep -vE "Pok[eé]"`
Expected: no output. Every hit is a miss.

- [ ] **Step 5: Lint and build**

```bash
cd frontend && npm run lint && npm run build
```
Expected: both pass.

- [ ] **Step 6: Walk every screen**

Start backend and frontend. Visit, and read every label on:
- Sessions list, and the new-session form
- Session detail, including adding a round
- Decks list, in both grid and list view, inside and outside a folder
- Deck builder, including the import/export dialog and the version list
- Deck stats
- Card search, and a card's detail

Expected: no Spanish anywhere, and no `undefined` where a label should be.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/
git commit -m "refactor: translate the interface copy to English"
```

---

## Task 14: Translate the agent and skill instructions, and close the plan

**Files:**
- Modify: `.claude/agents/log-mentor.md` (188 lines, 75 with Spanish)
- Modify: `.claude/skills/log-mentor/SKILL.md` (51 lines, 20 with Spanish)
- Modify: `docs/architecture.md` if any file's stated purpose changed wording
- Modify: `docs/operations.md` if it quotes a UI string

**Interfaces:**
- Consumes: nothing
- Produces: a repository with no Spanish outside a UI translation that does not exist yet

- [ ] **Step 1: Translate the log-mentor agent definition and skill**

Both describe how learning-log entries are written. The entries themselves in `log_mentor/` are already English, so this removes the last inconsistency: Spanish instructions producing English output. Keep the frontmatter keys (`name`, `description`, `model`, `tools`) untouched — only their values and the body change.

- [ ] **Step 2: Sweep the whole repository**

```bash
git ls-files | grep -vE 'package-lock|\.venv' | xargs grep -nE "[áéíóúñ¡¿«»]" | grep -vE "Pok[eé]"
```

Expected: no output, or only files whose Spanish is a deliberate example. Investigate every hit; do not accept one.

- [ ] **Step 3: Reconcile the docs with reality**

Re-read `docs/architecture.md` and `docs/operations.md`. Nothing structural moved, but if either quotes a UI string or an identifier that this plan renamed, fix it. A stale map is worse than no map.

- [ ] **Step 4: Full smoke test, backend and frontend together**

Start both. Repeat the screen walk from Task 13 Step 6, and additionally:
- Create a deck, add cards past the 4-copy limit, and read the violation — it must be English and come from the backend.
- Import a PTCG Live list and read the report.
- Delete a deck that a session used — the 409 must appear with an English message.

- [ ] **Step 5: Commit**

```bash
git add .claude/ docs/
git commit -m "refactor: translate agent and skill instructions to English"
```

- [ ] **Step 6: Write the learning-log entry**

Dispatch the `log-mentor` skill. The subagent never saw this session, so the dispatch prompt must carry what only exists here:

- The concept is **verifying a mechanical refactor without a test suite**: `ast.dump` with `include_attributes=False`, docstrings stripped from both trees, comparing working tree against a git ref.
- The harness was deliberately **not committed** — it is a tool for one job, and permanent cruft is a cost.
- Splitting the work **by risk rather than by directory** was the organising decision: prose (provable), identifiers (small, breakable), strings (visible). Say that the alternative — one commit per directory — was rejected because it mixes provable changes with breakable ones and destroys the value of a bisect.
- The AST harness was proved to fail before it was trusted (Task 2, Step 3). A verification tool that has never failed is not known to work.

---

## Done when

- `git ls-files | grep -vE 'package-lock|\.venv' | xargs grep -nE "[áéíóúñ¡¿«»]" | grep -vE "Pok[eé]"` returns nothing.
- `npm run lint` and `npm run build` pass.
- `backend/.venv/bin/python -c "import app.main"` succeeds.
- Every screen has been walked in a browser and shows English with no `undefined`.
- `CLAUDE.md` and `docs/decisions.md` state the new convention.

Then, and only then, start `docs/superpowers/plans/2026-08-28-i18n-locale-switch.md`.
