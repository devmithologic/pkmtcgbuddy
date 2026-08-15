/**
 * Acceso a /api/folders.
 *
 * El servidor devuelve las carpetas PLANAS, cada una con su `parent_id`. El
 * árbol se arma en el cliente con `buildTree`. Es la contrapartida de haber
 * elegido el modelo de «referencia al padre» en Mongo: barato de escribir,
 * y bajar por el árbol lo hace quien ya las tiene todas en memoria.
 */

import { request } from './client'

/** GET /api/folders — todas, planas, con el recuento de mazos directos. */
export function listFolders() {
  return request('/api/folders')
}

/**
 * El cuerpo va SERIALIZADO y con su cabecera.
 *
 * `request` pasa las opciones tal cual a `fetch`, y fetch no serializa objetos:
 * los convierte a texto con String(), así que un objeto llega literalmente como
 * "[object Object]". El síntoma es un 422 de FastAPI diciendo «body: Input
 * should be a valid dictionary», que no suena a lo que es.
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

/** PATCH /api/folders/{id} — renombrar o mover. */
export function updateFolder(folderId, changes) {
  return request(`/api/folders/${folderId}`, json('PATCH', changes))
}

/** DELETE /api/folders/{id} — el contenido sube al padre, no se borra. */
export function deleteFolder(folderId) {
  return request(`/api/folders/${folderId}`, { method: 'DELETE' })
}

/**
 * Convierte la lista plana en un árbol de `{...carpeta, children: []}`.
 *
 * Dos pasadas y no una búsqueda por cada padre: primero un índice por id, luego
 * se cuelga cada carpeta de su padre. Buscar el padre con `find()` dentro del
 * bucle sería O(n²) — irrelevante con diez carpetas, pero es el mismo reflejo
 * que evita el N+1 en el servidor, y aquí no cuesta nada hacerlo bien.
 *
 * Una carpeta cuyo `parent_id` no exista —no debería pasar, pero un borrado a
 * mano en mongosh lo provoca— se trata como raíz en vez de desaparecer. Los
 * datos huérfanos se muestran; esconderlos es cómo se pierden.
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
 * Aplana el árbol a `[{...carpeta, depth}]`, en el orden en que se pinta.
 *
 * Sirve para los desplegables de «mover a», donde hace falta una lista lineal
 * pero se quiere seguir viendo la jerarquía mediante la sangría.
 */
export function flattenTree(nodos, depth = 0) {
  return nodos.flatMap((n) => [{ ...n, depth }, ...flattenTree(n.children, depth + 1)])
}
