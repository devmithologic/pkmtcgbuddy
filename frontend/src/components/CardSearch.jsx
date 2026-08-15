import { useEffect, useState } from 'react'
import { searchCards } from '../api/cards'
import CardDetail from './CardDetail'

const DEBOUNCE_MS = 350

function emptyFilters(format) {
  return { q: '', format, category: '', ace_spec: false }
}

/**
 * Buscador de cartas contra TCGdex.
 *
 * Dos problemas que aparecen en cuanto una búsqueda se dispara al teclear, y que
 * este componente resuelve de forma explícita:
 *
 * 1. **Debounce.** Escribir "charizard" son nueve pulsaciones. Sin retardo, son
 *    nueve peticiones de las que solo importa la última. El temporizador reinicia
 *    en cada tecla y solo dispara cuando el usuario se detiene.
 *
 * 2. **Condición de carrera.** Las respuestas HTTP no llegan en el orden en que
 *    se pidieron. Si la búsqueda de "char" tarda 800ms y la de "charizard" 200ms,
 *    la lenta aterriza después y pisa los resultados correctos con los antiguos.
 *    AbortController cancela la anterior antes de lanzar la siguiente.
 */
export default function CardSearch({ onPick, defaultFormat = 'standard' }) {
  const [filters, setFilters] = useState(() => emptyFilters(defaultFormat))
  const [results, setResults] = useState([])
  const [hasMore, setHasMore] = useState(false)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [selectedId, setSelectedId] = useState(null)

  /**
   * Sigue al formato del mazo cuando este cambia.
   *
   * `useState(() => emptyFilters(defaultFormat))` solo corre AL MONTAR, así que
   * al cambiar el mazo a Expanded el buscador se quedaba en Standard y ofrecía
   * cartas del formato equivocado — que es el error que más caro sale aquí,
   * porque la carta entra en la lista y solo lo dices el panel de validación
   * después.
   *
   * El efecto depende solo de `defaultFormat`, no de `filters`: si el usuario
   * cambia el desplegable a mano para curiosear otro formato, su elección se
   * respeta hasta que el mazo cambie de verdad.
   */
  useEffect(() => {
    setFilters((previous) => ({ ...previous, format: defaultFormat }))
    // La página actual deja de significar nada al cambiar el conjunto.
    setPage(1)
  }, [defaultFormat])

  // El backend exige 2 caracteres como mínimo; con menos, ni lo intentamos.
  const nameQuery = filters.q.trim()
  const hasUsableName = nameQuery.length >= 2
  const canSearch = hasUsableName || filters.ace_spec

  useEffect(() => {
    if (!canSearch) {
      setResults([])
      setHasMore(false)
      // Estos dos hacen falta porque este retorno anticipado se salta el
      // finally de más abajo. Si el usuario borra el texto mientras hay una
      // búsqueda en vuelo, la limpieza aborta la petición, el finally no
      // ejecuta setLoading(false) —está protegido por signal.aborted— y el
      // efecto sale por aquí: «Buscando…» se quedaría para siempre, y el error
      // de la búsqueda anterior seguiría en pantalla.
      setLoading(false)
      setError(null)
      return
    }

    // Cancela la petición en vuelo cuando el efecto vuelve a correr.
    const controller = new AbortController()

    const timer = setTimeout(async () => {
      setLoading(true)
      setError(null)

      try {
        const data = await searchCards(
          // Solo mandamos q si por sí solo supera el mínimo del backend. Con
          // «Solo ACE SPEC» marcado, canSearch es cierto aunque haya una única
          // letra escrita: enviarla provocaría un 422 y el usuario vería un
          // error de validación en bruto en vez de resultados.
          { ...filters, q: hasUsableName ? nameQuery : undefined, page },
          controller.signal,
        )
        setResults(data.cards)
        setHasMore(data.has_more)
      } catch (err) {
        // Abortar es una cancelación deliberada, no un fallo que mostrar.
        if (err.name !== 'AbortError') setError(err.message)
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    }, DEBOUNCE_MS)

    // Limpieza: cancela temporizador y petición. Se ejecuta antes de cada
    // re-ejecución del efecto y al desmontar, así que cubre los dos problemas.
    return () => {
      clearTimeout(timer)
      controller.abort()
    }
    // Cualquier cambio de filtro o de página relanza la búsqueda.
  }, [filters, page, canSearch, hasUsableName, nameQuery])

  function handleFilterChange(event) {
    const { name, value, type, checked } = event.target
    setFilters((previous) => ({
      ...previous,
      [name]: type === 'checkbox' ? checked : value,
    }))
    // Cambiar un filtro invalida la página actual: la página 3 de otra búsqueda
    // no significa nada.
    setPage(1)
  }

  return (
    <section className="card-search">
      <h2>Buscar cartas</h2>

      <div className="filters">
        <label>
          Nombre
          <input
            type="text"
            name="q"
            value={filters.q}
            onChange={handleFilterChange}
            placeholder="charizard"
          />
        </label>

        <label>
          Formato
          <select name="format" value={filters.format} onChange={handleFilterChange}>
            <option value="standard">Standard</option>
            <option value="expanded">Expanded</option>
            <option value="">Cualquiera</option>
          </select>
        </label>

        <label>
          Categoría
          <select name="category" value={filters.category} onChange={handleFilterChange}>
            <option value="">Todas</option>
            <option value="Pokemon">Pokémon</option>
            <option value="Trainer">Entrenador</option>
            <option value="Energy">Energía</option>
          </select>
        </label>

        <label className="checkbox">
          <input
            type="checkbox"
            name="ace_spec"
            checked={filters.ace_spec}
            onChange={handleFilterChange}
          />
          Solo ACE SPEC
        </label>
      </div>

      <p className="hint">
        La búsqueda es por subcadena: <code>rod</code> encuentra <code>Aerodactyl</code>.
      </p>

      {!canSearch && <p className="empty">Escribe al menos 2 letras, o marca «Solo ACE SPEC».</p>}
      {loading && <p>Buscando…</p>}
      {error && <p className="error">{error}</p>}

      {!loading && !error && canSearch && results.length === 0 && (
        <p className="empty">Ninguna carta coincide.</p>
      )}

      <ul className="card-grid">
        {results.map((card) => (
          <li key={card.id}>
            {/* Un solo componente, dos usos. Sin onPick es un buscador que
                abre el detalle; con onPick, un selector que añade al mazo.
                Duplicar el componente para el segundo caso habría duplicado
                también el debounce, la cancelación y la paginación. */}
            <button
              type="button"
              onClick={() => (onPick ? onPick(card) : setSelectedId(card.id))}
              title={onPick ? `Añadir ${card.name} al mazo` : card.name}
            >
              {card.image_url ? (
                // loading="lazy" evita descargar 24 imágenes de golpe: el
                // navegador solo pide las que entran en pantalla.
                <img src={card.image_url} alt={card.name} loading="lazy" />
              ) : (
                <span className="no-image">sin imagen</span>
              )}
              <span className="card-name">{card.name}</span>
            </button>
          </li>
        ))}
      </ul>

      {canSearch && (page > 1 || hasMore) && (
        <div className="pagination">
          <button type="button" disabled={page === 1} onClick={() => setPage((p) => p - 1)}>
            Anterior
          </button>
          <span>Página {page}</span>
          <button type="button" disabled={!hasMore} onClick={() => setPage((p) => p + 1)}>
            Siguiente
          </button>
        </div>
      )}

      {selectedId && !onPick && (
        <CardDetail cardId={selectedId} onClose={() => setSelectedId(null)} />
      )}
    </section>
  )
}
