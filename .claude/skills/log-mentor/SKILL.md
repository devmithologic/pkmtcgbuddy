---
name: log-mentor
description: Writes a learning-log entry into `log_mentor/` documenting a code change and the concepts behind it — reference-style, concise, with links to official docs. Use this right after writing or modifying code that introduces a concept the developer hasn't met yet in this repo (a new FastAPI dependency, a Mongo aggregation stage, a React hook, a CORS setting, an async pattern, a Pydantic validator). Also use whenever the user says "document this", "log this change", "explain what we just built", "add this to the log", or asks for study notes on something just implemented. Default to using it after a vertical slice lands, even if nobody asked — the point of this repo is learning, and an undocumented concept is a lost lesson.
---

# Log Mentor

## Why this exists

This repo's governing rule (see `CLAUDE.md`) is that the developer is here to *learn* full-stack
development; the Pokémon TCG app is the vehicle. Code that works but whose mechanism is opaque is a
failed change here.

A log entry is how a change stops being "something Claude did" and becomes something the developer
owns. Write for the developer six months from now, who remembers the app but not why
`Depends()` existed — and who will search the web for these same terms.

## When to write an entry

Write one when a change **introduces or meaningfully exercises a concept**: the first async endpoint,
the first `motor` query, the first `useEffect` with a cleanup function, the first CORS middleware,
the first aggregation pipeline, the first custom Pydantic validator.

Do **not** write one for: renames, typo fixes, formatting, adding a field to an existing model, or a
second endpoint that repeats a pattern already logged. Repetition of a documented concept is not a
new lesson, and a log full of filler stops being read. If the change is a *variation* on a logged
concept, prefer adding a short section to the existing entry over creating a new file.

One entry covers **one concept**. If a slice introduced three (async I/O, CORS, and the repository
pattern), that is three files. Splitting them keeps each file findable by its title, which is the
whole point of the naming scheme.

## File location and naming

All entries live in `log_mentor/` at the repo root. Create the folder if it doesn't exist.

```
log_mentor/
  01_FASTAPI_ASYNC_ENDPOINTS.md
  02_MONGODB_DOCUMENT_MODELING.md
  03_REACT_USEEFFECT_CLEANUP.md
```

Format: `XX_LANG_CONCEPT.md`

- **`XX`** — zero-padded running index, in creation order. Find the next one by listing the folder
  and taking the highest existing index plus one; start at `01` when the folder is empty. Indexes are
  never reused or renumbered — they are a timeline, so a reader can see the order in which ideas were
  met.
- **`LANG`** — the language or stack layer the concept belongs to, uppercase. Use the existing
  vocabulary rather than inventing synonyms, so files sort and filter cleanly:
  `PYTHON`, `FASTAPI`, `PYDANTIC`, `MONGODB`, `PYMONGO`, `REACT`, `JAVASCRIPT`, `VITE`, `HTTP`,
  `DOCKER`, `PYTEST`, `GIT`. Add a new one only when nothing fits.
- **`CONCEPT`** — the concept in `SCREAMING_SNAKE_CASE`. Name the *idea*, not the file you touched:
  `DEPENDENCY_INJECTION`, not `MAIN_PY_CHANGES`. If you can't name the concept, that's a signal the
  change may not deserve an entry.

## Sourcing

Ground every entry in primary sources. Fetch the real documentation with **Context7**
(`resolve-library-id` then `query-docs`) before writing — the API surface of FastAPI, Pydantic,
React, and Motor moves faster than memory, and an entry that teaches a deprecated signature is worse
than no entry. Use WebFetch for specs and MDN when Context7 has no coverage.

Every entry carries **at least two reference links**, and they must be *primary*: official docs, the
relevant RFC or WHATWG spec, MDN, or the library's own source. Blog posts and tutorials are allowed
only as a third link when they genuinely add something the official docs don't. Deep-link to the
exact page — `https://fastapi.tiangolo.com/tutorial/dependencies/` teaches; a link to the homepage
does not.

## Voice

Aim for the register of a good reference article — GeeksforGeeks or MDN, not a blog post and not a
changelog. Concretely:

- **Lead with the definition.** First sentence says what the thing *is*, in one line, without
  metaphor. The reader who already knows it should be able to stop reading there.
- **Then the mechanism.** What actually happens at runtime, in order. This is the part that makes the
  concept transferable to another project.
- **Then our code.** Only after the general idea is established, show what we wrote. This ordering is
  deliberate: the concept is the durable knowledge; our file is just where the developer happened to
  meet it.
- **Use the industry term and say it plainly** — *dependency injection*, *ASGI*, *preflight request*,
  *N+1 query*, *optimistic UI*. Bold it on first use. Searchable vocabulary is half the skill.
- **Be short.** 80–150 lines. Every paragraph either explains a mechanism or shows code. Cut anything
  that reads as narration of what we did during the session.
- No emoji, no "Let's dive in", no congratulating the reader.

## Entry template

```markdown
# <Concept in Title Case>

> **Stack:** <LANG> · **Introduced in:** <what change prompted this> · **Date:** <YYYY-MM-DD>

## Definition

One or two sentences. What the concept is, stated flatly.

## Why it exists

The problem it solves. Ideally: what the code looks like *without* it, and what goes wrong.

## How it works

The mechanism, step by step. A short, minimal, generic snippet — not our code yet. If order or
timing matters (event loop, request lifecycle, render cycle), spell out the sequence.

## In this project

The actual code from this change, with the file path as a heading or comment. Point at the specific
lines that embody the concept and explain what each is doing.

```python
# backend/app/routers/matches.py
...
```

## Gotchas

Failure modes: what breaks, the error message you'd actually see, and why. This is the section the
developer will come back for.

## Related concepts

Neighbouring ideas worth knowing, and links to sibling entries: `see 02_MONGODB_DOCUMENT_MODELING.md`.

## References

- [Exact page title](https://official-docs-url) — official documentation
- [Spec or MDN page](https://url) — <what it covers>
```

Sections may be dropped when a concept genuinely has nothing to say there (a trivial concept may have
no gotchas), but `Definition`, `In this project`, and `References` always appear — they are what makes
the file a learning artifact rather than a note.

## Workflow

1. Identify the concept(s) the change introduced. Name each one in industry terms.
2. Decide honestly whether each deserves an entry (see *When to write an entry*).
3. List `log_mentor/` to find the next index.
4. Fetch official docs via Context7 for each concept.
5. Write the file(s) using the template.
6. Tell the developer which files you created, in one line each — not a summary of their contents.
   They're going to read the file; don't make them read it twice.

For a full worked entry, see `references/example_entry.md`.
