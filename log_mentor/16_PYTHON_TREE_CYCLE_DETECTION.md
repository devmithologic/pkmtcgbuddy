# Tree Cycle Detection

> **Stack:** PYTHON · **Introduced in:** Folder move validation · **Date:** 2026-08-15

## Definition

A **cycle** in a tree is a path that leads back to itself — moving folder A into its own descendant B closes a loop. **Cycle detection** is an algorithm that tests whether an operation would introduce a cycle before allowing it. Without this check, a tree silently becomes a graph, and nodes no longer reachable from the root vanish from listings without being deleted.

## Why it exists

In a parent-reference tree (see `15_MONGODB_TREE_PARENT_REFERENCES.md`), any node can be moved by changing its `parent_id`. A naive implementation accepts any parent ID:

```python
# Naive: no validation
async def move_folder(folder_id, new_parent_id):
    await folders.update_one(
        {"_id": folder_id},
        {"$set": {"parent_id": new_parent_id}}
    )
```

Imagine a folder structure:
```
Root
  Standard
    Modern
```

If you move "Standard" to be a child of "Modern", the graph is now:
```
Root
  Modern
    Standard        ← Standard's parent_id = Modern._id
      Modern        ← Modern's parent_id = Standard._id (cycle)
```

Neither "Standard" nor "Modern" now have a path back to the root. When the UI walks up each folder to assemble the breadcrumb, it enters an infinite loop. When you iterate the tree to render it, the cycle hangs the browser.

The cycle also corrupts the data silently: no document is deleted, but the folders are unreachable and disappear from listings, so the user loses access without understanding why.

## How it works

Before accepting a move, walk upward from the proposed parent toward the root. If the walk encounters the folder being moved, the move would close a cycle — reject it. If the walk reaches the root without meeting the folder, the tree remains acyclic.

The algorithm terminates because the existing tree has no cycles (enforced by this same check on every prior operation), so each upward step gets strictly closer to the root.

```
Is moving folder A under folder B safe?
│
└─ Walk upward from B: B → B.parent → B.parent.parent → … → root
   │
   └─ If we encounter A during the walk, A is already an ancestor of B.
      Making B a child of A would create: A → B → A (cycle).
      Reject the move.
   │
   └─ If we reach root without meeting A, the tree stays acyclic.
      Accept the move.
```

## In this project

**Function** (`backend/app/db/folder_repository.py`):
```python
async def crearia_ciclo(folder_id: ObjectId, nuevo_padre: ObjectId | None) -> bool:
    """Would moving `folder_id` under `nuevo_padre` create a cycle?
    
    This is the check that distinguishes a tree from a graph. Without it, the
    structure silently corrupts: dragging 'Competitive' into its own child
    'Standard' leaves both outside the tree (neither hangs off root anymore),
    so they vanish from listings without being deleted, and traversing the
    cycle to render it hangs the browser.
    
    Solved by walking upward from the proposed parent toward the root: if we
    encounter the folder itself, the branch would close on itself. Always
    terminates because the existing tree has no cycles and each step walks up.
    """
    if nuevo_padre is None:
        return False  # Moving to root is always safe
    if nuevo_padre == folder_id:
        return True   # Can't move into yourself

    padres = await _mapa_de_padres()  # Fetch parent map once
    actual = nuevo_padre
    while actual is not None:
        if actual == folder_id:
            return True  # Cycle detected
        actual = padres.get(actual)  # Walk up
    return False  # Reached root safely
```

**Usage** (`backend/app/routers/folders.py`):
```python
@router.patch("/{folder_id}")
async def update_folder(folder_id: str, payload: FolderUpdate):
    folder_oid = ObjectId(folder_id)
    
    # Check before write: prevents the corruption and avoids undo logic
    if payload.parent_id is not None:
        new_parent_oid = ObjectId(payload.parent_id)
        if await crearia_ciclo(folder_oid, new_parent_oid):
            raise HTTPException(status_code=409, detail="Would create a cycle")
    
    await repository.update_folder(folder_oid, payload)
    return {"success": True}
```

**Frontend safeguard** (`frontend/src/components/DeckList.jsx`):
```javascript
// After rendering the tree, omit impossible move destinations
const impossible = new Set()
function marcar_imposibles(node) {
  impossible.add(node.id)
  if (node.children) node.children.forEach(marcar_imposibles)
}
if (renaming?.kind === 'folder') {
  const node = porId.get(renaming.id)
  if (node) marcar_imposibles(node)
}

// The folder picker omits any id in `impossible`
```

The frontend prevents cycles from being offered (courtesy), but the server enforces it (authority). A malicious or buggy client cannot corrupt the tree.

## Gotchas

**Check-then-write needs no undo.** If the check runs before the write and passes, the write is guaranteed safe. There is no race condition: the tree cannot change in the microseconds between the check and the write (or if it does, the write either succeeds safely or the check must run again). This is why `crearia_ciclo()` runs as a separate call before `update_folder()`, not inside it.

**Fetching the parent map costs one query.** A naive loop that calls `get_folder(actual)` in the `while` loop would issue one query per step — N+1 again. Fetch the map once and walk it in memory.

**This check only prevents cycles at move time.** It does not prevent a document from being manually edited in the database with an invalid `parent_id`. The defense is operational: never expose raw database access to code that can be subverted. The check is correctness, not security.

## Related concepts

The tree structure this protects: see `15_MONGODB_TREE_PARENT_REFERENCES.md`.

## References

- [Cycle Detection Algorithms](https://en.wikipedia.org/wiki/Cycle_detection) — Wikipedia overview of algorithmic approaches
- [MongoDB Constraints and Validation](https://www.mongodb.com/docs/manual/core/schema-validation/) — server-side validation patterns (alternative to application-level checks)
