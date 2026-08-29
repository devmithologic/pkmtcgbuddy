/**
 * Access to /api/folders.
 *
 * The server returns folders FLAT, each with its `parent_id`. The tree is
 * built on the client with `buildTree`. That's the trade-off of having chosen
 * the "parent reference" model in Mongo: cheap to write, and walking down the
 * tree is done by whoever already has them all in memory.
 */

import { request } from './client'

/** GET /api/folders — all of them, flat, with the count of direct decks. */
export function listFolders() {
  return request('/api/folders')
}

/**
 * The body goes SERIALIZED and with its header.
 *
 * `request` passes options straight through to `fetch`, and fetch doesn't
 * serialize objects: it converts them to text with String(), so an object
 * arrives literally as "[object Object]". The symptom is a FastAPI 422
 * saying "body: Input should be a valid dictionary", which doesn't sound
 * like what it is.
 */
function json(method, body) {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }
}

/** POST /api/folders */
export function createFolder(folder) {
  return request('/api/folders', json('POST', folder))
}

/** PATCH /api/folders/{id} — rename or move. */
export function updateFolder(folderId, changes) {
  return request(`/api/folders/${folderId}`, json('PATCH', changes))
}

/** DELETE /api/folders/{id} — its contents move up to the parent, not deleted. */
export function deleteFolder(folderId) {
  return request(`/api/folders/${folderId}`, { method: 'DELETE' })
}

/**
 * Converts the flat list into a tree of `{...folder, children: []}`.
 *
 * Two passes rather than a lookup per parent: first an index by id, then
 * each folder is hung off its parent. Finding the parent with `find()`
 * inside the loop would be O(n²) — irrelevant with ten folders, but it's the
 * same reflex that avoids the N+1 on the server, and here it costs nothing
 * to do it right.
 *
 * A folder whose `parent_id` doesn't exist —shouldn't happen, but a manual
 * delete in mongosh causes it— is treated as a root instead of disappearing.
 * Orphaned data is shown; hiding it is how it gets lost.
 */
export function buildTree(folders) {
  const porId = new Map(folders.map((f) => [f.id, { ...f, children: [] }]))
  const raices = []

  for (const nodo of porId.values()) {
    const padre = nodo.parent_id ? porId.get(nodo.parent_id) : null
    if (padre) padre.children.push(nodo)
    else raices.push(nodo)
  }
  return raices
}

/**
 * Flattens the tree to `[{...folder, depth}]`, in the order it's rendered.
 *
 * Used by the "move to" dropdowns, where a linear list is needed but the
 * hierarchy still needs to show through indentation.
 */
export function flattenTree(nodos, depth = 0) {
  return nodos.flatMap((n) => [{ ...n, depth }, ...flattenTree(n.children, depth + 1)])
}
