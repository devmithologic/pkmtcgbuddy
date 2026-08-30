import { useEffect, useState } from 'react'
import { getDeckStats } from '../api/decks'
import { listTags } from '../api/sessions'
import { SESSION_TYPES } from '../sessionTypes'
import { useT } from '../i18n/index.jsx'

/**
 * How many games it takes before a percentage starts to mean something.
 *
 * It's not a statistical rule, it's a visual warning: 100% of 1 game and
 * 62% of 26 read the same if you only look at the number. Rows below this
 * threshold are flagged so they aren't mistaken for a trend.
 */
const MIN_SAMPLE = 5

const EMPTY_FILTERS = { date_from: '', date_to: '', session_type: '', tag: '' }

function pct(rate) {
  return `${Math.round(rate * 100)}%`
}

/** A row: label, bar proportional to the win rate, record and percentage. */
function Row({ label, line, sub }) {
  const thin = line.played < MIN_SAMPLE

  return (
    <li className={`stat-row ${thin ? 'is-thin' : ''}`}>
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
  const t = useT()
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
      .then((tagList) => active && setTags(tagList))
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
  if (!stats) return <p>{t('deckStats.loading')}</p>

  const { overall, by_version: byVersion, by_archetype: byArchetype } = stats
  const noData = overall.played === 0

  return (
    <section className="deck-stats">
      <div className="stats-filters">
        <label>
          {t('deckStats.from')}
          <input type="date" name="date_from" value={filters.date_from} onChange={handleFilter} />
        </label>
        <label>
          {t('deckStats.to')}
          <input type="date" name="date_to" value={filters.date_to} onChange={handleFilter} />
        </label>
        <label>
          {t('deckStats.eventType')}
          <select name="session_type" value={filters.session_type} onChange={handleFilter}>
            <option value="">{t('deckStats.allEventTypes')}</option>
            {SESSION_TYPES.map((value) => (
              <option key={value} value={value}>
                {t(`sessionType.${value}`)}
              </option>
            ))}
          </select>
        </label>
        {tags.length > 0 && (
          <label>
            {t('deckStats.tag')}
            <select name="tag" value={filters.tag} onChange={handleFilter}>
              <option value="">{t('deckStats.allTags')}</option>
              {tags.map((tagItem) => (
                <option key={tagItem.tag} value={tagItem.tag}>
                  {tagItem.tag} ({tagItem.sessions})
                </option>
              ))}
            </select>
          </label>
        )}

        {(filters.date_from || filters.date_to || filters.session_type || filters.tag) && (
          <button type="button" className="clear" onClick={() => setFilters(EMPTY_FILTERS)}>
            {t('deckStats.clear')}
          </button>
        )}
      </div>

      {noData ? (
        <p className="empty">{t('deckStats.noData')}</p>
      ) : (
        <>
          <div className="overall">
            <span className="overall-pct">{pct(overall.win_rate)}</span>
            <span className="overall-record">
              {overall.wins}–{overall.losses}–{overall.ties}
            </span>
            <span className="overall-sub">
              {/* Two quantities, two plural entries: `count` only ever picks one
                  category, so `played` and `playedAcross` are separate keys, each
                  pluralised on its own number, joined as fragments. That's safe
                  here specifically because a noun phrase followed by a
                  prepositional phrase keeps its order in both English and
                  Spanish, and each fragment is a whole phrase rather than a stem
                  needing a suffix glued on. */}
              {t('deckStats.played', { count: overall.played })}{' '}
              {t('deckStats.playedAcross', { count: stats.sessions_counted })}
              {loading && t('deckStats.updating')}
            </span>
          </div>

          {/* By version comes first on purpose: it's the question no other
              tracker answers, and the reason versioning exists. */}
          <h3>{t('deckStats.byVersion')}</h3>
          <ul className="stat-list">
            {byVersion.map((v) => (
              <Row key={v.version_id} label={`v${v.version}`} sub={v.message} line={v} />
            ))}
          </ul>
          {byVersion.length === 1 && (
            <p className="hint">{t('deckStats.singleVersionNote')}</p>
          )}

          <h3>{t('deckStats.byOpponent')}</h3>
          <ul className="stat-list">
            {byArchetype.map((a) => (
              <Row key={a.label} label={a.label} line={a} />
            ))}
          </ul>

          <h3>{t('deckStats.byEventType')}</h3>
          <ul className="stat-list">
            {stats.by_session_type.map((row) => (
              <Row
                key={row.label}
                // row.label comes from the backend and isn't guaranteed to be
                // a known session type — a stale value from before a type was
                // renamed, for instance. Only translate what's recognized;
                // otherwise fall back to the raw label rather than printing a
                // raw catalogue key.
                label={SESSION_TYPES.includes(row.label) ? t(`sessionType.${row.label}`) : row.label}
                line={row}
              />
            ))}
          </ul>

          <p className="hint">{t('deckStats.dimmedRowNote', { minSample: MIN_SAMPLE })}</p>
        </>
      )}
    </section>
  )
}
