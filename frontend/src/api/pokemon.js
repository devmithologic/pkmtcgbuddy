/** Acceso a /api/pokemon. Solo búsqueda: es un catálogo de referencia. */

import { queryString, request } from './client'

/**
 * GET /api/pokemon — busca por nombre, por subcadena.
 *
 * Acepta AbortSignal porque se dispara al teclear y las respuestas pueden
 * llegar desordenadas. Ver log_mentor/09.
 */
export function searchPokemon(q, signal) {
  return request(`/api/pokemon${queryString({ q })}`, { signal })
}
