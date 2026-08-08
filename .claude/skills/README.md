# Project skills

Skills are packaged instructions Claude Code loads on demand. Each one lives in its own folder here
and is described by a `SKILL.md` file:

```
.claude/skills/
  README.md          <- this file
  _template/
    SKILL.md         <- copy this to start a new skill
  log-mentor/
    SKILL.md
    references/
      example_entry.md
```

## Skills in this repo

- **`log-mentor`** — writes a learning-log entry into `log_mentor/` for each change that introduces a
  new concept, in reference-documentation style with links to primary sources. Triggers on its own
  after a slice lands; also on "document this" / "log this change".

## How a skill works

`SKILL.md` starts with YAML frontmatter and is followed by the instructions themselves:

```markdown
---
name: run-dev
description: Start the FastAPI backend and the React dev server together. Use when asked to run,
  start, or preview the app locally.
---

# Steps

1. ...
```

- **`name`** — kebab-case, matches the folder name. This is what `/name` invokes.
- **`description`** — the only part loaded into context by default. It decides whether the skill gets
  used, so write it for matching: say what the skill does *and* when to reach for it, including the
  words someone would actually type.
- **Body** — the full instructions, loaded only once the skill is invoked. Keep it to what isn't
  already obvious from the code.

## When to add one

Add a skill when a procedure is (a) repeated, and (b) not derivable from reading the repo. Good
candidates for this project as it grows:

- `run-dev` — the exact commands and order for starting backend + frontend + Mongo.
- `add-endpoint` — the house pattern for a new FastAPI route: model, router, test, frontend client.
- `tcg-data` — where card data comes from, rate limits, and how it's cached.

Don't add a skill for something the code already documents clearly — a stale skill is worse than
none.

## Keeping them honest

Skills rot. When a command, path, or convention changes, update the skill in the same change. If a
skill turns out to be wrong or unused, delete it.
