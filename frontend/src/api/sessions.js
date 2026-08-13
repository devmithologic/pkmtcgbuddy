/**
 * Acceso a /api/sessions.
 *
 * Las partidas viven bajo la sesión, no como recurso propio: no existe
 * `/api/matches`. Cada operación sobre una ronda devuelve la SESIÓN entera ya
 * actualizada, así que el cliente nunca recalcula el récord.
 */

import { request } from './client'

const json = (method, body) => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

/** GET /api/sessions — listado con mazo y récord. */
export function listSessions() {
  return request('/api/sessions')
}

/** GET /api/sessions/{id} — sesión con sus rondas. */
export function getSession(sessionId) {
  return request(`/api/sessions/${sessionId}`)
}

/** POST /api/sessions — crea una sesión vacía. */
export function createSession(payload) {
  return request('/api/sessions', json('POST', payload))
}

/**
 * PATCH /api/sessions/{id} — corrige fecha, tipo, mazo, nombre o notas.
 *
 * Solo la cabecera del evento. Las rondas tienen sus propios endpoints porque
 * cada una se guarda al añadirla.
 */
export function updateSession(sessionId, changes) {
  return request(`/api/sessions/${sessionId}`, json('PATCH', changes))
}

/** POST /api/sessions/{id}/matches — añade una ronda al final. */
export function addMatch(sessionId, match) {
  return request(`/api/sessions/${sessionId}/matches`, json('POST', match))
}

/** PUT /api/sessions/{id}/matches/{round} — corrige una ronda. */
export function updateMatch(sessionId, round, match) {
  return request(`/api/sessions/${sessionId}/matches/${round}`, json('PUT', match))
}

/** DELETE /api/sessions/{id}/matches/{round} — borra y renumera las siguientes. */
export function deleteMatch(sessionId, round) {
  return request(`/api/sessions/${sessionId}/matches/${round}`, { method: 'DELETE' })
}
