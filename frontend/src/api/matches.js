/**
 * Acceso a /api/matches. Ningún componente llama a fetch directamente.
 */

import { request } from './client'

/** GET /api/matches — todas las partidas, de la más reciente a la más antigua. */
export function listMatches() {
  return request('/api/matches')
}

/** POST /api/matches — registra una partida y devuelve la creada, ya con su id. */
export function createMatch(match) {
  return request('/api/matches', {
    method: 'POST',
    // Esta cabecera convierte la petición en "no simple" y obliga al navegador a
    // hacer un preflight OPTIONS antes del POST real. Es la razón de que el
    // backend necesite CORSMiddleware.
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(match),
  })
}
