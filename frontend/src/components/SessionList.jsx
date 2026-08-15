import { useEffect, useState } from 'react'
import { listDecks } from '../api/decks'
import { createSession, deleteSession, listSessions, listTags } from '../api/sessions'
import PokemonPair from './PokemonPair'
import Menu from './Menu'
import TagInput from './TagInput'
import { SESSION_TYPES, TYPE_LABEL } from '../sessionTypes'

/**
 * Hoy, en la zona horaria del usuario.
 *
 * toISOString() da la fecha UTC, y aquí estamos en UTC-6: a las 21:59 del día 12
 * devuelve "2026-08-13". Justo la hora a la que se registra una liga de entre
 * semana, así que la sesión nacía con la fecha de mañana.
 *
 * 'en-CA' se usa porque su formato de fecha es exactamente YYYY-MM-DD, que es lo
 * que espera <input type="date">.
 */
function today() {
  return new Date().toLocaleDateString('en-CA')
}

/**
 * Función y no constante: `const EMPTY = {played_at: today()}` se evalúa UNA vez
 * al cargar el módulo, así que una pestaña abierta desde ayer seguiría
 * proponiendo la fecha de ayer.
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

/** Listado de sesiones y formulario para abrir una nueva. */
export default function SessionList({ onOpen }) {
  const [sessions, setSessions] = useState([])
  const [decks, setDecks] = useState([])
  const [form, setForm] = useState(emptyForm)
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
    <section className="screen-split">
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

      {/* Todo lo que no es el formulario va junto en una columna. El envoltorio
          hace falta porque .screen-split es una rejilla y sus hijos DIRECTOS son
          las celdas: sin él, los filtros, el título y la lista serían tres
          celdas sueltas y se repartirían por las columnas. */}
      <div className="pane">
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

              {/* El mazo: sus dos Pokémon encima del nombre. El par de iconos
                  identifica un mazo más rápido que su nombre escrito, que es
                  para lo que existen. */}
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

            {/* La confirmación sigue existiendo: el menú cambia de dónde sale la
                acción, no que borrar un torneo de cinco rondas sea
                irreversible. */}
            {confirming === s.id ? (
              <span className="confirm-delete">
                ¿Borrar?
                <button type="button" onClick={() => handleDelete(s.id)}>Sí</button>
                <button type="button" onClick={() => setConfirming(null)}>No</button>
              </span>
            ) : (
              <Menu
                label={`Acciones de ${s.name || s.played_at}`}
                actions={[
                  {
                    icon: '✏️',
                    label: 'Editar',
                    // El segundo argumento abre la sesión con el formulario de
                    // cabecera ya desplegado, en vez de duplicarlo aquí.
                    onSelect: () => onOpen(s.id, true),
                  },
                  {
                    icon: '✕',
                    label: 'Borrar',
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
