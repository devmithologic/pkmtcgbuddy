/**
 * HTTP client shared by the modules in src/api/.
 *
 * It was extracted from matches.js when cards.js appeared and both needed
 * the same error handling. It wasn't created "just in case": the duplication
 * existed first.
 */

const API_URL = import.meta.env.VITE_API_URL

/**
 * Wrapper around fetch that turns error responses into exceptions.
 *
 * Reminder of why it's needed: **fetch does NOT reject on 4xx or 5xx**. It
 * only rejects if the request failed to complete. See
 * log_mentor/05_JAVASCRIPT_FETCH_ERROR_HANDLING.md
 *
 * @param {string} path  path under the API, e.g. '/api/cards'
 * @param {RequestInit} [options]  supports `signal` to cancel via AbortController
 */
export async function request(path, options) {
  const response = await fetch(`${API_URL}${path}`, options)

  if (!response.ok) {
    throw new Error(await errorMessage(response))
  }

  // 204 No Content carries no body, so response.json() would throw
  // "Unexpected end of JSON input". DELETE returns it, saying "done" with
  // nothing to deliver: returning the resource that was just deleted would
  // be contradictory.
  if (response.status === 204) return null

  return response.json()
}

/** Builds a query string, omitting null, undefined, '' and false. */
export function queryString(params) {
  const search = new URLSearchParams()

  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === '' || value === false) {
      continue
    }
    search.set(key, String(value))
  }

  const encoded = search.toString()
  return encoded ? `?${encoded}` : ''
}

/** Extracts a readable message from FastAPI's error body. */
async function errorMessage(response) {
  const fallback = `${response.status} ${response.statusText}`

  try {
    const body = await response.json()

    // 422 validation error: detail is an array of {loc, msg, type}.
    if (Array.isArray(body.detail)) {
      return body.detail.map((e) => `${e.loc?.join('.')}: ${e.msg}`).join(' · ')
    }
    return body.detail ?? fallback
  } catch {
    // The body wasn't JSON: a proxy's error page, for example.
    return fallback
  }
}
