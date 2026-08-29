/** Access to /api/pokemon. Search only: it's a reference catalog. */

import { queryString, request } from './client'

/**
 * GET /api/pokemon — searches by name, by substring.
 *
 * Accepts AbortSignal because it fires while typing and responses can arrive
 * out of order. See log_mentor/09.
 */
export function searchPokemon(q, signal) {
  return request(`/api/pokemon${queryString({ q })}`, { signal })
}
