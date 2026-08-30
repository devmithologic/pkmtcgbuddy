import { useEffect, useState } from 'react'
import { listDecks } from '../api/decks'
import { createSession, deleteSession, listSessions, listTags } from '../api/sessions'
import PokemonPair from './PokemonPair'
import Menu from './Menu'
import TagInput from './TagInput'
import { SESSION_TYPES } from '../sessionTypes'
import { useT } from '../i18n/index.jsx'

/**
 * Today, in the user's time zone.
 *
 * toISOString() gives the UTC date, and here we're in UTC-6: at 21:59 on the
 * 12th it returns "2026-08-13". Exactly the time a weekday league gets logged,
 * so the session was being born with tomorrow's date.
 *
 * 'en-CA' is used because its date format is exactly YYYY-MM-DD, which is
 * what <input type="date"> expects.
 */
function today() {
  return new Date().toLocaleDateString('en-CA')
}

/**
 * A function, not a constant: `const EMPTY = {played_at: today()}` would be
 * evaluated ONCE when the module loads, so a tab left open since yesterday
 * would keep proposing yesterday's date.
 */
function emptyForm() {
  return {
    played_at: today(),
    session_type: 'league',
    deck_id: '',
    name: '',
    tags: [],
  }
}

/** Session listing and the form to start a new one. */
export default function SessionList({ onOpen }) {
  const t = useT()
  const [sessions, setSessions] = useState([])
  const [decks, setDecks] = useState([])
  const [form, setForm] = useState(emptyForm)
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState(null)
  const [tags, setTags] = useState([])
  // Tag being filtered on, or null to see them all.
  const [filterTag, setFilterTag] = useState(null)
  // Session pending delete confirmation. The confirmation goes IN THE ROW and
  // not in a window.confirm: a browser dialog blocks the page and gets
  // dismissed out of habit, and this is irreversible.
  const [confirming, setConfirming] = useState(null)

  async function reload(tag = filterTag) {
    const [s, tagList] = await Promise.all([listSessions(tag ?? undefined), listTags()])
    setSessions(s)
    setTags(tagList)
  }

  useEffect(() => {
    let active = true

    // The three requests go together: none depends on the others.
    Promise.all([listSessions(filterTag ?? undefined), listDecks(), listTags()])
      .then(([s, d, t]) => {
        if (!active) return
        setSessions(s)
        setDecks(d)
        setTags(t)
      })
      .catch((err) => active && setError(err.message))
      .finally(() => active && setLoading(false))

    return () => {
      active = false
    }
  }, [filterTag])

  async function handleDelete(id) {
    setError(null)
    try {
      await deleteSession(id)
      setConfirming(null)
      await reload()
    } catch (err) {
      setError(err.message)
    }
  }

  // The DECK is what's chosen, and its current version is what gets saved,
  // same as before: you play with the list you have today.
  const selectedDeck = decks.find((d) => d.id === form.deck_id)

  function handleChange(event) {
    const { name, value } = event.target
    setForm((previous) => ({ ...previous, [name]: value }))
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setCreating(true)
    setError(null)

    try {
      const created = await createSession({
        played_at: form.played_at,
        session_type: form.session_type,
        deck_version_id: selectedDeck.current_version_id,
        name: form.name.trim() || null,
        tags: form.tags,
      })
      // It opens directly: a freshly created session is empty, and the only
      // thing that makes sense next is adding rounds to it.
      onOpen(created.id)
    } catch (err) {
      setError(err.message)
    } finally {
      setCreating(false)
    }
  }

  return (
    <section className="screen-split">
      <form onSubmit={handleSubmit} className="match-form">
        <h2>{t('sessionList.newSession')}</h2>

        <label>
          {t('sessionList.labelDate')}
          <input
            type="date"
            name="played_at"
            value={form.played_at}
            onChange={handleChange}
            required
          />
        </label>

        <label>
          {t('sessionList.labelType')}
          <select name="session_type" value={form.session_type} onChange={handleChange}>
            {SESSION_TYPES.map((value) => (
              <option key={value} value={value}>
                {t(`sessionType.${value}`)}
              </option>
            ))}
          </select>
        </label>

        <label>
          {t('sessionList.labelDeck')}
          <select name="deck_id" value={form.deck_id} onChange={handleChange} required>
            <option value="">{t('sessionList.placeholderDeck')}</option>
            {decks.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name} (v{d.current_version})
              </option>
            ))}
          </select>
        </label>

        <label>
          {t('sessionList.labelName')} <span className="optional">{t('common.optional')}</span>
          <input
            type="text"
            name="name"
            value={form.name}
            onChange={handleChange}
            placeholder="League Cup Guadalajara"
          />
        </label>

        <label>
          {t('sessionList.labelTags')} <span className="optional">{t('sessionList.placeholderTags')}</span>
          <TagInput
            value={form.tags}
            suggestions={tags}
            onChange={(newTags) => setForm({ ...form, tags: newTags })}
          />
        </label>

        {decks.length === 0 && !loading && (
          <p className="hint">{t('sessionList.deckRequired')}</p>
        )}

        <button type="submit" disabled={creating || !form.deck_id}>
          {creating ? t('sessionList.creating') : t('sessionList.startSession')}
        </button>

        {error && <p className="error">{error}</p>}
      </form>

      {/* Everything that isn't the form goes together in one column. The
          wrapper is needed because .screen-split is a grid and its DIRECT
          children are the cells: without it, the filters, the title and the
          list would be three loose cells and would get spread across the
          columns. */}
      <div className="pane">
      {tags.length > 0 && (
        <div className="tag-filters">
          <button
            type="button"
            className={filterTag === null ? 'active' : ''}
            onClick={() => setFilterTag(null)}
          >
            {t('sessionList.filterAll')}
          </button>
          {tags.map((tagItem) => (
            <button
              key={tagItem.tag}
              type="button"
              className={filterTag === tagItem.tag ? 'active' : ''}
              onClick={() => setFilterTag(tagItem.tag)}
            >
              {tagItem.tag} <span className="tag-count">{tagItem.sessions}</span>
            </button>
          ))}
        </div>
      )}

      <h2>
        {t('sessionList.sessionsTitle', { count: sessions.length })}
        {filterTag && <span className="filtered-by"> · {filterTag}</span>}
      </h2>
      {loading && <p>{t('sessionList.loading')}</p>}
      {!loading && sessions.length === 0 && (
        <p className="empty">{t('sessionList.noSessions')}</p>
      )}

      <ul className="session-list">
        {sessions.map((s) => (
          <li key={s.id} className="session-row">
            <button type="button" onClick={() => onOpen(s.id)}>
              <span className="s-date">{s.played_at}</span>
              <span className={`s-type s-type--${s.session_type}`}>
                {t(`sessionType.${s.session_type}`)}
              </span>
              <span className="s-name">{s.name || s.deck_name}</span>

              {/* The deck: its two Pokémon above the name. The pair of icons
                  identifies a deck faster than its written name, which is
                  what they exist for. */}
              <span className="s-deck">
                <span className="pkm-slot">
                  <PokemonPair
                    primary={s.deck_primary}
                    secondary={s.deck_secondary}
                    size={30}
                    variant="art"
                  />
                </span>
                <span className="s-deck-name">
                  {s.deck_name} <span className="vtag">v{s.deck_version}</span>
                </span>
              </span>

              <span className="s-record">
                {s.record.wins}–{s.record.losses}–{s.record.ties}
              </span>
            </button>

            {/* The confirmation still exists: the menu changes where the
                action is triggered from, not the fact that deleting a
                five-round tournament is irreversible. */}
            {confirming === s.id ? (
              <span className="confirm-delete">
                {t('sessionList.confirmDelete')}
                <button type="button" onClick={() => handleDelete(s.id)}>{t('common.yes')}</button>
                <button type="button" onClick={() => setConfirming(null)}>{t('common.no')}</button>
              </span>
            ) : (
              <Menu
                label={t('sessionList.rowActions', { name: s.name || s.played_at })}
                actions={[
                  {
                    icon: '✏️',
                    label: t('sessionList.editSession'),
                    // The second argument opens the session with the header
                    // form already expanded, instead of duplicating it here.
                    onSelect: () => onOpen(s.id, true),
                  },
                  {
                    icon: '✕',
                    label: t('sessionList.deleteSession'),
                    danger: true,
                    onSelect: () => setConfirming(s.id),
                  },
                ]}
              />
            )}
          </li>
        ))}
      </ul>
      </div>
    </section>
  )
}
