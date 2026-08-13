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
