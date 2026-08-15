/**
 * Acceso a /api/decks.
 *
 * A diferencia de las cartas, los mazos son datos nuestros: aquí sí hay
 * escrituras.
 */

import { queryString, request } from './client'

/** GET /api/decks — todos los mazos con su estado de validez. */
export function listDecks() {
  return request('/api/decks')
}

/** GET /api/decks/{id} — mazo, lista de la versión actual y validación. */
export function getDeck(deckId) {
  return request(`/api/decks/${deckId}`)
}

/**
 * POST /api/decks — crea un mazo con su versión 1, vacía.
 *
 * Recibe el objeto entero y lo manda entero. La primera versión desestructuraba
 * `{ name, deck_format }`, y cuando el formulario ganó los dos iconos de Pokémon
 * se quedaron por el camino: el mazo se creaba sin ellos y nadie avisaba.
 *
 * Es el mismo fallo que tuvo add_match en el repositorio de sesiones. Enumerar
 * campos —al desestructurar aquí, al construir un documento allí— crea un filtro
 * silencioso que hay que recordar actualizar cada vez que el modelo crece. Quien
 * valida qué campos son válidos es el backend, que para eso tiene el modelo.
 */
export function createDeck(deck) {
  return request('/api/decks', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(deck),
  })
}

/**
 * PUT /api/decks/{id}/cards — reemplaza la lista de la versión actual.
 *
 * Se manda la lista entera, no «suma una Iono». Eso hace la operación
 * idempotente: repetirla no duplica nada, y no hace falta coordinar contadores.
 * Devuelve el mazo ya validado, así que el cliente no tiene que recalcular nada.
 */
export function saveDeckCards(deckId, cards) {
  return request(`/api/decks/${deckId}/cards`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ cards }),
  })
}

/** POST /api/decks/{id}/versions — nueva versión copiando la actual. */
export function createVersion(deckId, message) {
  return request(`/api/decks/${deckId}/versions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  })
}

/** GET /api/decks/{id}/versions — historial. */
export function listVersions(deckId) {
  return request(`/api/decks/${deckId}/versions`)
}

/** GET /api/decks/{id}/versions/{vid} — una versión concreta con su lista. */
export function getVersion(deckId, versionId) {
  return request(`/api/decks/${deckId}/versions/${versionId}`)
}

/**
 * GET /api/decks/{id}/stats — estadísticas agregadas del mazo.
 *
 * Acepta AbortSignal porque los filtros disparan una consulta nueva y las
 * respuestas pueden llegar desordenadas.
 */
export function getDeckStats(deckId, filters = {}, signal) {
  return request(`/api/decks/${deckId}/stats${queryString(filters)}`, { signal })
}

/**
 * PATCH /api/decks/{id} — cambia nombre o iconos de un mazo existente.
 *
 * PATCH y no PUT porque se manda solo lo que cambia. El backend usa
 * exclude_unset, así que enviar {name} no borra los iconos.
 */
export function updateDeck(deckId, changes) {
  return request(`/api/decks/${deckId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(changes),
  })
}

/**
 * DELETE /api/decks/{id} — borra el mazo y su historial de versiones.
 *
 * Puede fallar con 409 si alguna sesión se jugó con él. No es un error del
 * cliente que haya que evitar preguntando antes: es la respuesta correcta, y el
 * mensaje que trae dice cuántas sesiones lo usan. `request` ya lo convierte en
 * una excepción con ese texto.
 */
export function deleteDeck(deckId) {
  return request(`/api/decks/${deckId}`, { method: 'DELETE' })
}

/**
 * POST /api/decks/import — crea un mazo desde una lista en texto.
 *
 * Devuelve `{deck, imported_cards, unresolved}`. `unresolved` llega siempre,
 * aunque venga vacío: quien pega 60 cartas tiene derecho a saber si entraron 60
 * o 57, y cuáles no, escritas tal como las mandó.
 */
export function importDeck(payload) {
  return request('/api/decks/import', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

/**
 * GET /api/decks/{id}/export — la lista en texto, lista para pegar.
 *
 * No pasa por `request`: ese envoltorio hace response.json(), y esto es
 * text/plain. Un documento, no un dato.
 */
export async function exportDeck(deckId) {
  const response = await fetch(`${import.meta.env.VITE_API_URL}/api/decks/${deckId}/export`)
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`)
  return response.text()
}
