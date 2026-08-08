/**
 * Único punto del frontend que habla con el backend.
 *
 * Los componentes importan estas funciones y nunca llaman a fetch directamente.
 * La razón es concreta: si mañana cambia una ruta, se añade autenticación o hay
 * que reintentar peticiones, se toca este fichero y ninguno más.
 */

const API_URL = import.meta.env.VITE_API_URL

/**
 * Envoltorio sobre fetch que traduce respuestas de error a excepciones.
 *
 * Existe por un comportamiento de fetch que sorprende a casi todo el mundo:
 * **fetch NO lanza error en respuestas 4xx o 5xx**. Un 500 del servidor devuelve
 * una promesa resuelta con normalidad. Solo rechaza si la petición no llegó a
 * completarse — sin red, DNS caído, CORS bloqueado.
 *
 * Sin la comprobación de response.ok, un error del servidor pasaría inadvertido y
 * el fallo aparecería mucho más tarde, al intentar usar datos que no existen.
 */
async function request(path, options) {
  const response = await fetch(`${API_URL}${path}`, options)

  if (!response.ok) {
    throw new Error(await errorMessage(response))
  }

  return response.json()
}

/** Extrae un mensaje legible del cuerpo de error de FastAPI. */
async function errorMessage(response) {
  const fallback = `${response.status} ${response.statusText}`

  try {
    const body = await response.json()

    // FastAPI responde {"detail": ...}. Para un 422 de validación, detail es un
    // array de objetos con la ruta del campo y el motivo; para los errores que
    // lanzamos con HTTPException, es una cadena.
    if (Array.isArray(body.detail)) {
      return body.detail.map((e) => `${e.loc?.join('.')}: ${e.msg}`).join(' · ')
    }
    return body.detail ?? fallback
  } catch {
    // El cuerpo no era JSON (por ejemplo, una página de error de un proxy).
    return fallback
  }
}

/** GET /api/matches — todas las partidas, de la más reciente a la más antigua. */
export function listMatches() {
  return request('/api/matches')
}

/** POST /api/matches — registra una partida y devuelve la creada, ya con su id. */
export function createMatch(match) {
  return request('/api/matches', {
    method: 'POST',
    // Esta cabecera es la que convierte la petición en "no simple" y obliga al
    // navegador a hacer un preflight OPTIONS antes del POST real. Es la razón de
    // que el backend necesite CORSMiddleware.
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(match),
  })
}
