# MongoDB Tree: Parent References

> **Stack:** MONGODB · **Introduced in:** Deck folder organization · **Date:** 2026-08-15

## Definition

A **tree structure** in a document database is a way to model hierarchical relationships — folders containing folders, categories containing subcategories, organizational hierarchies. MongoDB offers five competing approaches; **parent references** store a `parent_id` field on each node pointing to its parent, making upward traversal trivial and downward traversal (finding all descendants) expensive by requiring a graph search.

## Why it exists

Relationships in a document database are not enforced like foreign keys in SQL. Five patterns exist, each making a different query cheap:

| Pattern | Cheap query | Expensive query | Trade-off |
| --- | --- | --- | --- |
| **Parent references** | Walk up to root | Find all descendants | Good for small trees |
| Ancestor array | Find descendants with `$in` | Move a node (rewrite all children) | Requires array index |
| Materialized path | Find subtree with regex prefix | Move a node (rewrite all children) | String parsing needed |
| Child references | Find children | Walk to root | Inverse of parent refs |
| Nested sets | Range queries on tree | Any write operation | Complex math |

The choice hinges on collection size and query patterns. In this project: ten folders, all operations fetch the entire collection, and moving a folder is rare. Fetching ten documents is instant; optimizing expensive queries on small data is machinery that costs more than it saves.

## How it works

Each document holds a `parent_id` that references another document's `_id`. The root node has `parent_id: null`. To walk up the tree to the root, follow `parent_id` → `parent_id` → `null`. To find descendants, you must traverse every node and test whether its `parent_id` eventually points to your target — that is, walk up from each candidate and check if you reach your node.

Because the existing tree has no cycles (a prerequisite for any tree), each upward walk terminates reliably and the search always completes.

## In this project

**Model** (`backend/app/models/folder.py`):
```python
class FolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    parent_id: str | None = None  # null means root

class FolderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    parent_id: str | None = None  # None is meaningful: "move to root"
    # exclude_unset distinguishes "not sent" from "sent as null"
```

**Queries** (`backend/app/db/folder_repository.py`):
```python
async def list_folders() -> list[dict]:
    """All folders with deck count.
    
    Two queries for the entire tree regardless of size — this is why parent
    references work here. A small collection means fetching all and assembling
    the tree in memory is cheaper than indexes and subqueries.
    """
    folders = [doc async for doc in _collection().find().sort("name", ASCENDING)]
    
    # Count decks per folder via aggregation, not a loop
    # (avoid N+1 query).
    cursor = await get_database()[DECKS].aggregate(
        [
            {"$match": {"folder_id": {"$ne": None}}},
            {"$group": {"_id": "$folder_id", "n": {"$sum": 1}}},
        ]
    )
    counts = {d["_id"]: d["n"] async for d in cursor}
    
    for folder in folders:
        folder["deck_count"] = counts.get(folder["_id"], 0)
    return folders
```

**Frontend tree assembly** (`frontend/src/components/DeckList.jsx`):
```javascript
// Build the tree from flat parent references, then flatten it for display
const porId = new Map(folders.map((f) => [f.id, f]))
const tree = buildTree(folders)
const flat = flattenTree(tree)

// Walk up from current folder to root for breadcrumb
function ruta(id) {
  const path = []
  let current = id ? porId.get(id) : null
  while (current) {
    path.unshift(current)
    current = current.parent_id ? porId.get(current.parent_id) : null
  }
  return path
}
```

The UI shows one folder at a time with a breadcrumb, like a file manager — navigation is stateful, not a tree display. This design removes the need for a folder selector in the create form (the navigation already says where you are) and eliminates edge cases.

## Gotchas

**Do not use parent references for large collections.** At 100,000 folders, fetching them all to assemble the tree becomes prohibitive. Switch to ancestor arrays or materialized paths, accepting the cost of moving a node.

**Do not add cycles.** A cycle breaks the tree silently — nodes no longer reachable from the root vanish from listings without being deleted, and traversing a cycle in the UI hangs the browser. See `crearia_ciclo()` in the sibling entry.

**Null parent is a meaningful value.** When updating, `parent_id: null` means "move to root", distinct from "parent_id not provided" (ignore the field). Use `exclude_unset` to distinguish them in Pydantic models.

## Related concepts

The cycle check that prevents a tree from becoming a graph: see `16_PYTHON_TREE_CYCLE_DETECTION.md`.

## References

- [Tree Structures: Parent References](https://www.mongodb.com/docs/manual/tutorial/model-tree-structures-with-parent-references/) — MongoDB tutorial covering parent references, queries, and indexing
- [Model Tree Structures](https://www.mongodb.com/docs/manual/tutorial/model-tree-structures/) — MongoDB documentation overview of all five tree structure patterns
