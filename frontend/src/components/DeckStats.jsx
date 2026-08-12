import { useEffect, useState } from 'react'
import { getDeckStats } from '../api/decks'
import { SESSION_TYPES, TYPE_LABEL } from '../sessionTypes'

/**
 * A partir de cuántas partidas un porcentaje empieza a significar algo.
 *
 * No es una regla estadística, es una advertencia visual: 100% de 1 partida y
 * 62% de 26 se leen igual si solo miras el número. Los renglones por debajo de
 * este umbral se marcan para que no se confundan con una tendencia.
 */
const MUESTRA_MINIMA = 5

const EMPTY_FILTERS = { date_from: '', date_to: '', session_type: '' }

function pct(rate) {
  return `${Math.round(rate * 100)}%`
}

/** Un renglón: etiqueta, barra proporcional al win rate, récord y porcentaje. */
function Row({ label, line, sub }) {
  const escasa = line.played < MUESTRA_MINIMA

  return (
    <li className={`stat-row ${escasa ? 'is-thin' : ''}`}>
      <span className="stat-label">
        {label}
        {sub && <span className="stat-sub">{sub}</span>}
      </span>

      {/* La barra es refuerzo visual del porcentaje que ya está escrito al
          lado, así que se oculta a lectores de pantalla. */}
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
 * Estadísticas de un mazo.
 *
 * Nada se calcula aquí: el servidor agrega y devuelve los números hechos. Es la
 * misma regla que la validación del mazo y el récord de la sesión — una sola
 * implementación del cálculo, imposible que dos discrepen.
 */
export default function DeckStats({ deckId }) {
  const [stats, setStats] = useState(null)
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)

    getDeckStats(deckId, filters, controller.signal)
      .then(setStats)
      .catch((err) => {
        if (err.name !== 'AbortError') setError(err.message)
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })

    // Cambiar un filtro cancela la consulta anterior: las respuestas pueden
    // llegar desordenadas. Ver log_mentor/09.
    return () => controller.abort()
  }, [deckId, filters])

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
        {(filters.date_from || filters.date_to || filters.session_type) && (
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

          {/* Por versión va primero a propósito: es la pregunta que ningún otro
              tracker responde, y la razón de que exista el versionado. */}
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
