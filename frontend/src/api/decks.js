/**
 * Acceso a /api/decks.
 *
 * A diferencia de las cartas, los mazos son datos nuestros: aquí sí hay
 * escrituras.
 */

import { request } from './client'

/** GET /api/decks — todos los mazos con su estado de validez. */
export function listDecks() {
  return request('/api/decks')
}

/** GET /api/decks/{id} — mazo, lista de la versión actual y validación. */
export function getDeck(deckId) {
  return request(`/api/decks/${deckId}`)
}

/** POST /api/decks — crea un mazo con su versión 1, vacía. */
export function createDeck({ name, deck_format }) {
  return request('/api/decks', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, deck_format }),
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
