import { useEffect, useState } from 'react'
import { getDeckStats } from '../api/decks'
import { listTags } from '../api/sessions'
import { SESSION_TYPES, TYPE_LABEL } from '../sessionTypes'

/**
 * How many games it takes before a percentage starts to mean something.
 *
 * It's not a statistical rule, it's a visual warning: 100% of 1 game and
 * 62% of 26 read the same if you only look at the number. Rows below this
 * threshold are flagged so they aren't mistaken for a trend.
 */
const MUESTRA_MINIMA = 5

const EMPTY_FILTERS = { date_from: '', date_to: '', session_type: '', tag: '' }

function pct(rate) {
  return `${Math.round(rate * 100)}%`
}

/** A row: label, bar proportional to the win rate, record and percentage. */
function Row({ label, line, sub }) {
  const escasa = line.played < MUESTRA_MINIMA

  return (
    <li className={`stat-row ${escasa ? 'is-thin' : ''}`}>
      <span className="stat-label">
        {label}
        {sub && <span className="stat-sub">{sub}</span>}
      </span>

      {/* The bar is a visual reinforcement of the percentage already
          written next to it, so it's hidden from screen readers. */}
      <span className="stat-bar" aria-hidden="true">
        <span className="stat-bar-fill" style={{ width: pct(line.win_rate) }} />
      </span>

      <span className="stat-record">
        {line.wins}–{line.losses}–{line.ties}
      </span>
      <span className="stat-pct">{pct(line.win_rate)}</span>
    </li>
  )
}

/**
 * A deck's statistics.
 *
 * Nothing is computed here: the server aggregates and returns the numbers
 * already made. It's the same rule as deck validation and the session's
 * record — one single implementation of the calculation, impossible for
 * two to disagree.
 */
export default function DeckStats({ deckId }) {
  const [stats, setStats] = useState(null)
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [tags, setTags] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    // Clear the error on retry. Without this, a transient failure —
    // restarting the backend — left the panel stuck on the error message:
    // the component does `if (error) return`, so even if the next query
    // succeeded there was no way back short of unmounting.
    setError(null)

    getDeckStats(deckId, filters, controller.signal)
      .then(setStats)
      .catch((err) => {
        if (err.name !== 'AbortError') setError(err.message)
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })

    // Changing a filter cancels the previous query: responses can arrive
    // out of order. See log_mentor/09.
    return () => controller.abort()
  }, [deckId, filters])

  // Tags are loaded once: they don't depend on the deck or the filters.
  useEffect(() => {
    let active = true
    listTags()
      .then((t) => active && setTags(t))
      .catch(() => {})
    return () => {
      active = false
    }
  }, [])

  function handleFilter(event) {
    const { name, value } = event.target
    setFilters((previous) => ({ ...previous, [name]: value }))
  }

  if (error) return <p className="error">{error}</p>
  if (!stats) return <p>Cargando…</p>

  const { overall, by_version: byVersion, by_archetype: byArchetype } = stats
  const sinDatos = overall.played === 0

  return (
    <section className="deck-stats">
      <div className="stats-filters">
        <label>
          Desde
          <input type="date" name="date_from" value={filters.date_from} onChange={handleFilter} />
        </label>
        <label>
          Hasta
          <input type="date" name="date_to" value={filters.date_to} onChange={handleFilter} />
        </label>
        <label>
          Tipo de evento
          <select name="session_type" value={filters.session_type} onChange={handleFilter}>
            <option value="">Todos</option>
            {SESSION_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </label>
        {tags.length > 0 && (
          <label>
            Etiqueta
            <select name="tag" value={filters.tag} onChange={handleFilter}>
              <option value="">Todas</option>
              {tags.map((t) => (
                <option key={t.tag} value={t.tag}>
                  {t.tag} ({t.sessions})
                </option>
              ))}
            </select>
          </label>
        )}

        {(filters.date_from || filters.date_to || filters.session_type || filters.tag) && (
          <button type="button" className="clear" onClick={() => setFilters(EMPTY_FILTERS)}>
            limpiar
          </button>
        )}
      </div>

      {sinDatos ? (
        <p className="empty">
          Sin partidas para este recorte. Registra sesiones con este mazo en la pestaña Sesiones.
        </p>
      ) : (
        <>
          <div className="overall">
            <span className="overall-pct">{pct(overall.win_rate)}</span>
            <span className="overall-record">
              {overall.wins}–{overall.losses}–{overall.ties}
            </span>
            <span className="overall-sub">
              {overall.played} partidas en {stats.sessions_counted} sesion
              {stats.sessions_counted === 1 ? '' : 'es'}
              {loading && ' · actualizando…'}
            </span>
          </div>

          {/* By version comes first on purpose: it's the question no other
              tracker answers, and the reason versioning exists. */}
          <h3>Por versión</h3>
          <ul className="stat-list">
            {byVersion.map((v) => (
              <Row key={v.version_id} label={`v${v.version}`} sub={v.message} line={v} />
            ))}
          </ul>
          {byVersion.length === 1 && (
            <p className="hint">
              Con una sola versión no hay comparación posible todavía. Crea una nueva versión al
              cambiar cartas y estas cifras empezarán a decir si el cambio funcionó.
            </p>
          )}

          <h3>Por rival</h3>
          <ul className="stat-list">
            {byArchetype.map((a) => (
              <Row key={a.label} label={a.label} line={a} />
            ))}
          </ul>

          <h3>Por tipo de evento</h3>
          <ul className="stat-list">
            {stats.by_session_type.map((t) => (
              <Row key={t.label} label={TYPE_LABEL[t.label] ?? t.label} line={t} />
            ))}
          </ul>

          <p className="hint">
            Los renglones atenuados tienen menos de {MUESTRA_MINIMA} partidas: el porcentaje todavía
            no significa gran cosa.
          </p>
        </>
      )}
    </section>
  )
}
