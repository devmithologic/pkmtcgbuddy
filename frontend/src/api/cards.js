/**
 * Acceso a /api/cards.
 *
 * El backend hace de proxy sobre TCGdex, así que estas llamadas cuestan unos
 * 500ms. Eso condiciona la interfaz: hay que aplicar debounce al teclear y poder
 * cancelar peticiones que ya no interesan.
 */

import { queryString, request } from './client'

/**
 * GET /api/cards — busca cartas con filtros combinados por AND.
 *
 * @param {object} filters
 * @param {string} [filters.q]         parte del nombre, mínimo 2 caracteres
 * @param {string} [filters.format]    'standard' | 'expanded'
 * @param {string} [filters.category]  'Pokemon' | 'Trainer' | 'Energy'
 * @param {boolean} [filters.ace_spec] solo cartas ACE SPEC
 * @param {number} [filters.page]
 * @param {AbortSignal} [signal]  para cancelar si llega una búsqueda más nueva
 */
export function searchCards(filters, signal) {
  return request(`/api/cards${queryString(filters)}`, { signal })
}

/** GET /api/cards/{id} — detalle con rareza, marca de regulación y legalidad. */
export function getCard(cardId, signal) {
  return request(`/api/cards/${encodeURIComponent(cardId)}`, { signal })
}
