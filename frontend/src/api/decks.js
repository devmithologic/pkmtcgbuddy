/**
 * Access to /api/decks.
 *
 * Unlike cards, decks are our own data: here writes do happen.
 */

import { queryString, request } from './client'

/** GET /api/decks — all decks with their validity state. */
export function listDecks() {
  return request('/api/decks')
}

/** GET /api/decks/{id} — deck, current version's decklist, and validation. */
export function getDeck(deckId) {
  return request(`/api/decks/${deckId}`)
}

/**
 * POST /api/decks — creates a deck with its version 1, empty.
 *
 * Receives the whole object and sends it whole. The first version
 * destructured `{ name, deck_format }`, and when the form gained the two
 * Pokémon icons they were left behind: the deck was created without them and
 * nobody noticed.
 *
 * It's the same bug add_match had in the session repository. Enumerating
 * fields —destructuring here, building a document there— creates a silent
 * filter that has to be remembered and updated every time the model grows.
 * The backend is what decides which fields are valid, since that's what the
 * model is for.
 */
export function createDeck(deck) {
  return request('/api/decks', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(deck),
  })
}

/**
 * PUT /api/decks/{id}/cards — replaces the current version's decklist.
 *
 * The whole decklist is sent, not "add one Iono". That makes the operation
 * idempotent: repeating it duplicates nothing, and no counters need
 * coordinating. Returns the deck already validated, so the client doesn't
 * have to recompute anything.
 */
export function saveDeckCards(deckId, cards) {
  return request(`/api/decks/${deckId}/cards`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ cards }),
  })
}

/** POST /api/decks/{id}/versions — new version copying the current one. */
export function createVersion(deckId, message) {
  return request(`/api/decks/${deckId}/versions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  })
}

/** GET /api/decks/{id}/versions — history. */
export function listVersions(deckId) {
  return request(`/api/decks/${deckId}/versions`)
}

/** GET /api/decks/{id}/versions/{vid} — one specific version with its decklist. */
export function getVersion(deckId, versionId) {
  return request(`/api/decks/${deckId}/versions/${versionId}`)
}

/**
 * GET /api/decks/{id}/stats — the deck's aggregated statistics.
 *
 * Accepts AbortSignal because filters trigger a new query and responses can
 * arrive out of order.
 */
export function getDeckStats(deckId, filters = {}, signal) {
  return request(`/api/decks/${deckId}/stats${queryString(filters)}`, { signal })
}

/**
 * PATCH /api/decks/{id} — changes an existing deck's name or icons.
 *
 * PATCH and not PUT because only what changes is sent. The backend uses
 * exclude_unset, so sending {name} doesn't erase the icons.
 */
export function updateDeck(deckId, changes) {
  return request(`/api/decks/${deckId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(changes),
  })
}

/**
 * DELETE /api/decks/{id} — deletes the deck and its version history.
 *
 * Can fail with 409 if some session was played with it. That's not a client
 * error to be avoided by asking first: it's the correct response, and the
 * message it carries says how many sessions use it. `request` already turns
 * it into an exception with that text.
 */
export function deleteDeck(deckId) {
  return request(`/api/decks/${deckId}`, { method: 'DELETE' })
}

/**
 * POST /api/decks/import — creates a deck from a text decklist.
 *
 * Returns `{deck, imported_cards, unresolved}`. `unresolved` always arrives,
 * even if empty: someone who pastes 60 cards has the right to know whether 60
 * or 57 got in, and which ones didn't, written exactly as they sent them.
 */
export function importDeck(payload) {
  return request('/api/decks/import', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

/**
 * GET /api/decks/{id}/export — the decklist as text, ready to paste.
 *
 * Doesn't go through `request`: that wrapper does response.json(), and this
 * is text/plain. A document, not a piece of data.
 */
export async function exportDeck(deckId) {
  const response = await fetch(`${import.meta.env.VITE_API_URL}/api/decks/${deckId}/export`)
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`)
  return response.text()
}
