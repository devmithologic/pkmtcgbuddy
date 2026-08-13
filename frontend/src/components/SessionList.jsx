import { useEffect, useState } from 'react'
import { listDecks } from '../api/decks'
import { createSession, deleteSession, listSessions, listTags } from '../api/sessions'
import TagInput from './TagInput'
import { SESSION_TYPES, TYPE_LABEL } from '../sessionTypes'

function today() {
  return new Date().toISOString().slice(0, 10)
}

const EMPTY = {
  played_at: today(),
  session_type: 'league',
  deck_id: '',
  name: '',
  tags: [],
}

/** Listado de sesiones y formulario para abrir una nueva. */
export default function SessionList({ onOpen }) {
  const [sessions, setSessions] = useState([])
  const [decks, setDecks] = useState([])
  const [form, setForm] = useState(EMPTY)
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState(null)
  const [tags, setTags] = useState([])
  // Etiqueta por la que se filtra, o null para verlas todas.
  const [filterTag, setFilterTag] = useState(null)
  // Sesión pendiente de confirmar borrado. La confirmación va EN LA FILA y no
  // en un window.confirm: un diálogo del navegador bloquea la página y se
  // descarta por costumbre, y esto es irreversible.
  const [confirming, setConfirming] = useState(null)

  async function reload(tag = filterTag) {
    const [s, t] = await Promise.all([listSessions(tag ?? undefined), listTags()])
    setSessions(s)
    setTags(t)
  }

  useEffect(() => {
    let active = true

    // Las tres peticiones van juntas: ninguna depende de las otras.
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

  // Se elige el MAZO y se guarda su versión actual, igual que antes: juegas con
  // la lista que tienes hoy.
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
      // Se abre directamente: una sesión recién creada está vacía, y lo único
      // que tiene sentido a continuación es meterle rondas.
      onOpen(created.id)
    } catch (err) {
      setError(err.message)
    } finally {
      setCreating(false)
    }
  }

  return (
    <section>
      <form onSubmit={handleSubmit} className="match-form">
        <h2>Nueva sesión</h2>

        <label>
          Fecha
          <input
            type="date"
            name="played_at"
            value={form.played_at}
            onChange={handleChange}
            required
          />
        </label>

        <label>
          Tipo
          <select name="session_type" value={form.session_type} onChange={handleChange}>
            {SESSION_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </label>

        <label>
          Mazo
          <select name="deck_id" value={form.deck_id} onChange={handleChange} required>
            <option value="">— elige un mazo —</option>
            {decks.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name} (v{d.current_version})
              </option>
            ))}
          </select>
        </label>

        <label>
          Nombre <span className="optional">opcional</span>
          <input
            type="text"
            name="name"
            value={form.name}
            onChange={handleChange}
            placeholder="League Cup Guadalajara"
          />
        </label>

        <label>
          Etiquetas <span className="optional">opcional: tienda, propósito…</span>
          <TagInput
            value={form.tags}
            suggestions={tags}
            onChange={(t) => setForm({ ...form, tags: t })}
          />
        </label>

        {decks.length === 0 && !loading && (
          <p className="hint">Necesitas crear un mazo antes de registrar una sesión.</p>
        )}

        <button type="submit" disabled={creating || !form.deck_id}>
          {creating ? 'Creando…' : 'Empezar sesión'}
        </button>

        {error && <p className="error">{error}</p>}
      </form>

      {tags.length > 0 && (
        <div className="tag-filters">
          <button
            type="button"
            className={filterTag === null ? 'active' : ''}
            onClick={() => setFilterTag(null)}
          >
            Todas
          </button>
          {tags.map((t) => (
            <button
              key={t.tag}
              type="button"
              className={filterTag === t.tag ? 'active' : ''}
              onClick={() => setFilterTag(t.tag)}
            >
              {t.tag} <span className="tag-count">{t.sessions}</span>
            </button>
          ))}
        </div>
      )}

      <h2>
        Sesiones ({sessions.length})
        {filterTag && <span className="filtered-by"> · {filterTag}</span>}
      </h2>
      {loading && <p>Cargando…</p>}
      {!loading && sessions.length === 0 && (
        <p className="empty">Todavía no hay sesiones registradas.</p>
      )}

      <ul className="session-list">
        {sessions.map((s) => (
          <li key={s.id} className="session-row">
            <button type="button" onClick={() => onOpen(s.id)}>
              <span className="s-date">{s.played_at}</span>
              <span className={`s-type s-type--${s.session_type}`}>
                {TYPE_LABEL[s.session_type]}
              </span>
              <span className="s-name">{s.name || s.deck_name}</span>
              <span className="s-deck">
                {s.deck_name} <span className="vtag">v{s.deck_version}</span>
              </span>
              <span className="s-record">
                {s.record.wins}–{s.record.losses}–{s.record.ties}
              </span>
            </button>

            {confirming === s.id ? (
              <span className="confirm-delete">
                ¿Borrar?
                <button type="button" onClick={() => handleDelete(s.id)}>Sí</button>
                <button type="button" onClick={() => setConfirming(null)}>No</button>
              </span>
            ) : (
              <button
                type="button"
                className="delete-session"
                onClick={() => setConfirming(s.id)}
                aria-label={`Borrar la sesión ${s.name || s.played_at}`}
                title="Borrar sesión"
              >
                ×
              </button>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}
