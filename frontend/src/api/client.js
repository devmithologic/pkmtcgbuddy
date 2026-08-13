/**
 * Cliente HTTP compartido por los módulos de src/api/.
 *
 * Se extrajo de matches.js cuando apareció cards.js y ambos necesitaban el mismo
 * manejo de errores. No se creó "por si acaso": la duplicación existía primero.
 */

const API_URL = import.meta.env.VITE_API_URL

/**
 * Envoltorio sobre fetch que convierte respuestas de error en excepciones.
 *
 * Recordatorio de por qué hace falta: **fetch NO rechaza ante 4xx o 5xx**. Solo
 * rechaza si la petición no llegó a completarse. Ver
 * log_mentor/05_JAVASCRIPT_FETCH_ERROR_HANDLING.md
 *
 * @param {string} path  ruta bajo la API, por ejemplo '/api/cards'
 * @param {RequestInit} [options]  admite `signal` para cancelar con AbortController
 */
export async function request(path, options) {
  const response = await fetch(`${API_URL}${path}`, options)

  if (!response.ok) {
    throw new Error(await errorMessage(response))
  }

  // 204 No Content no trae cuerpo, así que response.json() lanzaría
  // "Unexpected end of JSON input". Lo devuelve DELETE, que dice "hecho" sin
  // nada que entregar: devolver el recurso recién borrado sería contradictorio.
  if (response.status === 204) return null

  return response.json()
}

/** Construye una query string omitiendo null, undefined, '' y false. */
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

/** Extrae un mensaje legible del cuerpo de error de FastAPI. */
async function errorMessage(response) {
  const fallback = `${response.status} ${response.statusText}`

  try {
    const body = await response.json()

    // 422 de validación: detail es un array de {loc, msg, type}.
    if (Array.isArray(body.detail)) {
      return body.detail.map((e) => `${e.loc?.join('.')}: ${e.msg}`).join(' · ')
    }
    return body.detail ?? fallback
  } catch {
    // El cuerpo no era JSON: página de error de un proxy, por ejemplo.
    return fallback
  }
}
