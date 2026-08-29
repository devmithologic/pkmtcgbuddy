/**
 * Access to /api/sessions.
 *
 * Matches live under the session, not as their own resource: `/api/matches`
 * doesn't exist. Every operation on a round returns the whole SESSION
 * already updated, so the client never recomputes the record.
 */

import { queryString, request } from './client'

const json = (method, body) => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

/** GET /api/sessions — listing with deck and record. */
export function listSessions(tag) {
  return request(`/api/sessions${queryString({ tag })}`)
}

/** GET /api/sessions/{id} — session with its rounds. */
export function getSession(sessionId) {
  return request(`/api/sessions/${sessionId}`)
}

/** POST /api/sessions — creates an empty session. */
export function createSession(payload) {
  return request('/api/sessions', json('POST', payload))
}

/**
 * PATCH /api/sessions/{id} — corrects date, type, deck, name or notes.
 *
 * Only the event's header. Rounds have their own endpoints because each one
 * is saved as it's added.
 */
export function updateSession(sessionId, changes) {
  return request(`/api/sessions/${sessionId}`, json('PATCH', changes))
}

/** POST /api/sessions/{id}/matches — adds a round at the end. */
export function addMatch(sessionId, match) {
  return request(`/api/sessions/${sessionId}/matches`, json('POST', match))
}

/** PUT /api/sessions/{id}/matches/{round} — corrects a round. */
export function updateMatch(sessionId, round, match) {
  return request(`/api/sessions/${sessionId}/matches/${round}`, json('PUT', match))
}

/** DELETE /api/sessions/{id}/matches/{round} — deletes and renumbers the following ones. */
export function deleteMatch(sessionId, round) {
  return request(`/api/sessions/${sessionId}/matches/${round}`, { method: 'DELETE' })
}

/** GET /api/sessions/tags — tags in use, with their session count. */
export function listTags() {
  return request('/api/sessions/tags')
}

/** DELETE /api/sessions/{id} — deletes the session and its rounds. Returns 204. */
export function deleteSession(sessionId) {
  return request(`/api/sessions/${sessionId}`, { method: 'DELETE' })
}
