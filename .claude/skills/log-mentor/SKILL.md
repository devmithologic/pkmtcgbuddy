---
name: log-mentor
description: Writes a learning-log entry into `log_mentor/` documenting a code change and the concepts behind it — reference-style, concise, with links to official docs. Use this right after writing or modifying code that introduces a concept the developer hasn't met yet in this repo (a new FastAPI dependency, a Mongo aggregation stage, a React hook, a CORS setting, an async pattern, a Pydantic validator). Also use whenever the user says "document this", "log this change", "explain what we just built", "add this to the log", or asks for study notes on something just implemented. Default to using it after a vertical slice lands, even if nobody asked — the point of this repo is learning, and an undocumented concept is a lost lesson.
---

# Log Mentor

This skill **does not write the documentation**. It dispatches the `log-mentor` subagent, which
runs on Haiku and has the full instructions — when an entry is warranted, the naming format, the
voice, the template — in `.claude/agents/log-mentor.md`.

## What to do

Call the Agent tool:

```
Agent(
  subagent_type: "log-mentor",
  description: "Document <concept>",
  prompt: "<the assignment, see below>"
)
```

## Rules

**Don't write the entry yourself.** You know how, and that's exactly why this has to be said: the
work goes to the subagent so it doesn't spend the working session's context on 150 lines of prose,
and so the more expensive model isn't used for a task that's writing against a fixed template. If
you start writing it, the whole point of dispatching is gone.

**Give it the scope in the prompt, not the content.** The agent figures out on its own what
changed — it reads the diff, `CLAUDE.md`, and the code comments — so don't summarize the change
for it. What it does need is to know *where to look*, because a large `git diff` can mix several
pieces of work:

- what was just touched ("the uncommitted changes in `backend/app/db/folder_repository.py` and
  `frontend/src/components/DeckList.jsx`"), or
- the commit range, if the work is already committed ("since `454f001`").

If something genuinely happened that isn't in the diff or in `CLAUDE.md` — an alternative that was
tried and discarded, a measurement that was taken and not written down — mention that: it's the
one thing the agent can't recover on its own.

**Run it in the background.** Don't wait on it, don't keep asking it, and **don't make up its
result**: the notification that it finished arrives on its own. When it does, say which files it
created, one line each. If it decided nothing deserved an entry, that counts too — it's a valid
outcome and often the right one.

**Only one for all the entries.** Even if the slice introduced three concepts, it's a single
agent: the template links sibling entries in "Related concepts," and whoever writes all three
knows what the other two say. It also means indexes `15`, `16`, `17` get handed out without
colliding, which three parallel agents can't guarantee.
