import { useEffect, useState } from 'react'
import { searchCards } from '../api/cards'
import CardDetail from './CardDetail'

const DEBOUNCE_MS = 350

const EMPTY_FILTERS = {
  q: '',
  format: 'standard',
  category: '',
  ace_spec: false,
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
export default function CardSearch() {
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [results, setResults] = useState([])
  const [hasMore, setHasMore] = useState(false)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [selectedId, setSelectedId] = useState(null)

  // El backend exige 2 caracteres como mínimo; con menos, ni lo intentamos.
  const canSearch = filters.q.trim().length >= 2 || filters.ace_spec

  useEffect(() => {
    if (!canSearch) {
      setResults([])
      setHasMore(false)
      return
    }

    // Cancela la petición en vuelo cuando el efecto vuelve a correr.
    const controller = new AbortController()

    const timer = setTimeout(async () => {
      setLoading(true)
      setError(null)

      try {
        const data = await searchCards(
          { ...filters, q: filters.q.trim() || undefined, page },
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
  }, [filters, page, canSearch])

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
            <button type="button" onClick={() => setSelectedId(card.id)}>
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

      {selectedId && <CardDetail cardId={selectedId} onClose={() => setSelectedId(null)} />}
    </section>
  )
}
