/**
 * Access to /api/cards.
 *
 * The backend proxies TCGdex, so these calls cost around 500ms. That shapes
 * the UI: typing needs debounce, and requests that are no longer wanted need
 * to be cancellable.
 */

import { queryString, request } from './client'

/**
 * GET /api/cards — search cards with filters combined by AND.
 *
 * @param {object} filters
 * @param {string} [filters.q]         part of the name, minimum 2 characters
 * @param {string} [filters.format]    'standard' | 'expanded'
 * @param {string} [filters.category]  'Pokemon' | 'Trainer' | 'Energy'
 * @param {boolean} [filters.ace_spec] ACE SPEC cards only
 * @param {number} [filters.page]
 * @param {AbortSignal} [signal]  to cancel if a newer search arrives
 */
export function searchCards(filters, signal) {
  return request(`/api/cards${queryString(filters)}`, { signal })
}

/** GET /api/cards/{id} — detail with rarity, regulation mark and legality. */
export function getCard(cardId, signal) {
  return request(`/api/cards/${encodeURIComponent(cardId)}`, { signal })
}
