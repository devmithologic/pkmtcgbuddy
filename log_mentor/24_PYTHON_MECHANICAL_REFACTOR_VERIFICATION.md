# Verification of Mechanical Refactors Without Tests

> **Stack:** PYTHON · **Introduced in:** feat/english-standard-and-i18n (tasks 2–14, commit b4f34f6) · **Date:** 2026-08-28

## Definition

**Mechanical verification** is a strategy for proving that a large, repetitive refactor — renaming thousands of identifiers, translating all prose, reformatting — has changed only what was intended to change, without a test suite to catch mistakes. It combines **structural equivalence checking** (comparing code at the AST level) with **manual audits** for each change type, and sequences commits by risk tier so that failures are immediately locatable by `git bisect`.

## Why it exists

A refactor touching 50+ files and changing 165+ identifiers plus every comment and string has too much surface area to review by eye. You cannot tell from a diff whether a renamed identifier was missed in one file, or whether a docstring lost a paragraph in translation. A test suite would catch some of these errors, but this repository had no tests at the start of the work.

The need is acute: rename a Python variable `carpeta` to `folder`, and if you miss one occurrence inside a string literal (say, `error_msg = "carpeta no existe"`) or in a comment-free context like a dictionary key, Python does not alert you — it simply reads a different variable or uses a literal string where code expected the variable. The program runs silently wrong until that code path is hit.

## How it works

### Part 1: AST-Equivalence Checking (Structural Verification)

**Abstract Syntax Tree** (**AST**) is the representation Python's parser produces: a tree of node types (`Module`, `FunctionDef`, `Assign`, `BinOp`, etc.) that captures every statement and expression, but not comment text or line numbers.

The `ast` module in the standard library can dump any tree to a string representation via `ast.dump()`. The key technique is a single flag: `include_attributes=False`.

**With `include_attributes=True` (the default):** The dump includes line numbers, column offsets, and character positions for every node. So when you rename `folder` back to `carpeta` or reformat a docstring from three lines to five, the dump changes — not because the statements differ, but because the physical location changed.

**With `include_attributes=False`:** The dump omits those numbers. A docstring that moves from lines 5–7 to 5–8 produces an identical dump. A variable renamed from `carpeta` to `folder` *does* produce a different dump — the identifier text is part of the node value, not an attribute. But a reformatted comment, or a docstring translated from Spanish to English, produces the **same dump**.

Procedure:

1. Parse the original file at a git base commit: `ast.parse(git_show(base + ":" + path))`
2. Parse the current working-tree version: `ast.parse(Path(path).read_text())`
3. Strip docstrings from both trees in place (see the blind spot, below).
4. Dump both with `include_attributes=False` and compare the strings.
5. If they differ, a statement changed — an `if` became a `while`, an operator flipped, a call was added or removed. If they match, every statement is identical.

This catches real mistakes instantly: a half-applied rename shows up as a different identifier value in the tree. It does not catch every kind of error (see the blind spot), but what it does catch, it catches always and at no runtime cost.

### Part 2: The Harness's Blind Spot — Docstring Content

Docstrings appear in the AST as the first expression in a function, class, or module body. When you strip them before comparing — which the harness does, by replacing `node.body[0]` if it is a docstring with nothing, or with a `Pass()` if stripping it would leave an empty body — you are left with an AST that is completely insensitive to docstring text.

This is **deliberate**, not a bug. The harness's job is to prove "no statements changed," not "the prose is perfect." The two are answering different questions.

But this means the harness is **structurally incapable** of detecting a docstring that was supposed to have three paragraphs and now has two. It will report `0 failures` happily, because no statement changed.

**Real consequence:** In the actual execution of this plan, Task 4 (translating `backend/app/db/` comments and docstrings) silently lost one paragraph of reasoning in a complex docstring. The harness reported success. The failure was caught by a **second, orthogonal check**: a manual paragraph-count comparison using `git show <base>:<path>` to count the blank-line-delimited blocks in the original and current versions. A count mismatch surfaced the loss immediately.

The lesson is not "the harness is broken." The lesson is: **An automated structural check and a content-completeness check answer different questions, and neither one substitutes for the other.** If your refactor touches prose, structure checking alone is insufficient — you must audit prose separately, using tools that understand prose.

### Part 3: Risk-Tiered Commit Sequencing

Rather than grouping commits by directory (all `backend/app/db/` in one commit, all `frontend/src/components/` in another), the work was split into three risk tiers:

1. **Prose only** — comments, docstrings, strings that are not behaviour. Provable by paragraph-count audits and human reading. Small in surface area per file.
2. **Identifiers** — renaming `carpeta` to `folder`, `fecha` to `date`. Small in line count per file (names are typically one per definition or occurrence), but breaks the program instantly and silently if done wrong. A missed rename in a string or a complex scope is invisible until that code path runs.
3. **User-visible strings** — the strings the frontend displays, API detail messages, violation messages. Highly visible (wrong text shows up on screen immediately), but risky — altering a string comparison, dropping a format placeholder, or changing a message's shape can break behaviour.

**Why three tiers, not three directories?**

If a single commit bundled all three (e.g., "refactor `backend/app/db/`"), then a failure found days later — a bug in behaviour, or a missed translation surface in a user-visible path — could have been caused by any of the three kinds of change. When you run `git bisect` to locate the commit that introduced the bug, you land on that commit and have no idea whether it was a prose error, a rename error, or a string change that caused it. You must read the diff and think.

When commits are tiered by risk, `git bisect` immediately tells you the *kind* of failure to expect:

- Did a prose-only commit break behaviour? Something is very wrong; the two should be unrelated.
- Did an identifier-rename commit introduce the bug? Look for missed renames or references that were not updated.
- Did a user-visible-string commit cause a behavioural change? Look for string comparisons, format placeholders, or conditional logic gated on the exact text.

This is not "a commit per file." A single tier commit may touch many files (the prose commit touched 40+ files). But every line in that commit answers the same risk question.

### Part 4: Verification Tool Testing

The harness itself was never committed to the repository. It was written in Task 2, used daily through Tasks 3–6 (the prose-only commits), and deleted when the work moved to identifier renaming (where the AST harness's job was complete).

Before relying on it, Task 2 included an explicit proof that the harness actually works:

1. **Step 2:** Run the harness against an unchanged tree. Expected result: `0 failures`. If this fails, the harness itself is broken.
2. **Step 3:** Deliberately introduce a real logic change — change `DECK_SIZE = 60` to `DECK_SIZE = 61`. Run the harness. Expected: it flags the file as a failure. **This is critical.** A verification tool that has never been observed to fail is not known to work. This is the mutation-testing principle: if your test cannot detect an intentional error, it cannot be trusted to detect real errors.
3. **Step 4:** Revert the change and verify the harness passes again. This confirms the tool is not stuck in a failure state.

Only after this explicit proof was the harness trusted for Tasks 3–6.

## In this project

The harness was written to Python in `verify_ast_equality.py` during Task 2 of the `feat/english-standard-and-i18n` branch. The full script appears in `docs/superpowers/plans/2026-08-28-english-standard.md`, Task 2, Step 1.

Core mechanics:

```python
# Strip docstrings to ignore prose-only changes
def strip_docstrings(tree: ast.AST) -> ast.AST:
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        body = node.body
        if (body and isinstance(body[0], ast.Expr) 
            and isinstance(body[0].value, ast.Constant) 
            and isinstance(body[0].value.value, str)):
            node.body = body[1:] or [ast.Pass()]  # Can't leave body empty
    return tree

def fingerprint(source: str) -> str:
    """Parse, strip docstrings, dump with no attributes, return string."""
    return ast.dump(strip_docstrings(ast.parse(source)))

# Usage:
before_dump = fingerprint(git_show(f"{base_ref}:path/to/file.py"))
after_dump = fingerprint(Path("path/to/file.py").read_text())
assert before_dump == after_dump, "A statement changed"
```

The harness ran after each of Tasks 3–6:

- Task 3 (model prose): 0 failures
- Task 4 (repository prose): 0 failures — though the paragraph-count audit found a lost paragraph in `card_repository.py`'s docstring
- Task 5 (service prose): 0 failures
- Task 6 (router prose and config): 0 failures

Then Tasks 7–14 changed identifiers and strings, so the harness would have flagged every change. Its role was complete.

## Gotchas

**Renaming inside strings:** If a local variable `carpeta` is renamed to `folder` but the code prints an error message `"Carpeta no existe"`, the program compiles and runs. The message still says "Carpeta" in Spanish. The runtime does not care. This is why identifier renaming is a separate risk tier — to catch these silent errors with a different verification strategy (linting, manual code review, smoke testing).

**Docstring content loss:** The harness passes even if a docstring shrinks from six paragraphs to three. The paragraphs were reasoning explaining a design decision — the code is correct, but the knowledge embedded in the docstring is gone. Use a paragraph-count audit in parallel with the structural check.

**No docstring for all callables:** If a function has no docstring (a helper function or a property), there is no docstring node to strip. The harness sees the first statement as usual. This is fine — most loss happens to *existing* docstrings, not to missing ones.

**Comments are invisible to AST:** Python's parser discards comments entirely. They never reach the AST. A comment can be translated, deleted, or rewritten without the harness seeing it — this is a feature (comments are the most noise-prone part of a refactor), but it means the harness tells you nothing about whether comment quality was preserved.

## Related concepts

- **`git bisect` and commit granularity** — The risk-tiering strategy's whole value comes from `git bisect`'s ability to tell you the *kind* of change that caused a failure. If your commits mix concerns, bisect gives you a pile of changes but no strategy for figuring out which was wrong.
- **AST-based analysis in general** — The `ast` module is used throughout Python tooling (linters, type checkers, code formatters) to understand code structure. This entry shows one application: equivalence checking for refactors.
- **Testing mutations** — The principle that a test never observed to fail is not proven to work. In this project, we proved the harness by breaking it on purpose before relying on it.

## References

- [Python `ast` module documentation](https://docs.python.org/3/library/ast.html) — the `ast.dump()` function and the `include_attributes` parameter
- [Python AST node types](https://docs.python.org/3/library/ast.html#abstract-grammar) — `Module`, `FunctionDef`, `Expr`, `Constant`, and others
- `docs/superpowers/plans/2026-08-28-english-standard.md` — the plan this methodology was built for, with all fourteen tasks and their verification steps
