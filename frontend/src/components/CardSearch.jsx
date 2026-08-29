import { useEffect, useState } from 'react'
import { searchCards } from '../api/cards'
import CardDetail from './CardDetail'

const DEBOUNCE_MS = 350

function emptyFilters(format) {
  return { q: '', format, category: '', ace_spec: false }
}

/**
 * Card search against TCGdex.
 *
 * Two problems that show up as soon as a search fires on every keystroke,
 * and that this component solves explicitly:
 *
 * 1. **Debounce.** Typing "charizard" is nine keystrokes. Without a delay,
 *    that's nine requests when only the last one matters. The timer resets
 *    on every keystroke and only fires once the user stops.
 *
 * 2. **Race condition.** HTTP responses don't arrive in the order they were
 *    requested. If the search for "char" takes 800ms and "charizard" takes
 *    200ms, the slow one lands afterward and overwrites the correct results
 *    with the stale ones. AbortController cancels the previous one before
 *    launching the next.
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
   * Follows the deck's format when it changes.
   *
   * `useState(() => emptyFilters(defaultFormat))` only runs ON MOUNT, so
   * when the deck changed to Expanded the search box stayed on Standard and
   * offered cards from the wrong format — which is the costliest mistake
   * here, because the card gets added to the list and only the validation
   * panel tells you about it afterward.
   *
   * The effect depends only on `defaultFormat`, not on `filters`: if the
   * user manually changes the dropdown to browse another format, their
   * choice is respected until the deck actually changes.
   */
  useEffect(() => {
    setFilters((previous) => ({ ...previous, format: defaultFormat }))
    // The current page stops meaning anything once the set changes.
    setPage(1)
  }, [defaultFormat])

  // The backend requires a minimum of 2 characters; with fewer, we don't
  // even try.
  const nameQuery = filters.q.trim()
  const hasUsableName = nameQuery.length >= 2
  const canSearch = hasUsableName || filters.ace_spec

  useEffect(() => {
    if (!canSearch) {
      setResults([])
      setHasMore(false)
      // These two are needed because this early return skips the finally
      // block further down. If the user clears the text while a search is
      // in flight, the cleanup aborts the request, the finally doesn't run
      // setLoading(false) — it's guarded by signal.aborted — and the effect
      // exits through here: "Searching…" would stay forever, and the
      // previous search's error would still be on screen.
      setLoading(false)
      setError(null)
      return
    }

    // Cancels the request in flight when the effect runs again.
    const controller = new AbortController()

    const timer = setTimeout(async () => {
      setLoading(true)
      setError(null)

      try {
        const data = await searchCards(
          // We only send q if it alone clears the backend's minimum. With
          // "Only ACE SPEC" checked, canSearch is true even with a single
          // letter typed: sending it would trigger a 422 and the user
          // would see a raw validation error instead of results.
          { ...filters, q: hasUsableName ? nameQuery : undefined, page },
          controller.signal,
        )
        setResults(data.cards)
        setHasMore(data.has_more)
      } catch (err) {
        // Aborting is a deliberate cancellation, not a failure to show.
        if (err.name !== 'AbortError') setError(err.message)
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    }, DEBOUNCE_MS)

    // Cleanup: cancels the timer and the request. Runs before every
    // re-run of the effect and on unmount, so it covers both problems.
    return () => {
      clearTimeout(timer)
      controller.abort()
    }
    // Any change to a filter or the page relaunches the search.
  }, [filters, page, canSearch, hasUsableName, nameQuery])

  function handleFilterChange(event) {
    const { name, value, type, checked } = event.target
    setFilters((previous) => ({
      ...previous,
      [name]: type === 'checkbox' ? checked : value,
    }))
    // Changing a filter invalidates the current page: page 3 of a
    // different search means nothing.
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
            {/* One single component, two uses. Without onPick it's a
                search box that opens the detail view; with onPick, a
                picker that adds to the deck. Duplicating the component for
                the second case would have also duplicated the debounce,
                the cancellation and the pagination. */}
            <button
              type="button"
              onClick={() => (onPick ? onPick(card) : setSelectedId(card.id))}
              title={onPick ? `Añadir ${card.name} al mazo` : card.name}
            >
              {card.image_url ? (
                // loading="lazy" avoids downloading 24 images at once: the
                // browser only requests the ones that enter the viewport.
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
