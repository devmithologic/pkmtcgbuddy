import { useEffect, useState } from 'react'
import { listDecks } from '../api/decks'
import { addMatch, deleteMatch, getSession, updateMatch, updateSession } from '../api/sessions'
import { SESSION_TYPES, TYPE_LABEL } from '../sessionTypes'
import PokemonPair from './PokemonPair'
import PokemonPicker from './PokemonPicker'

const RESULTS = [
  { value: 'win', label: 'Victoria' },
  { value: 'loss', label: 'Derrota' },
  { value: 'tie', label: 'Empate' },
]

const EMPTY_ROUND = {
  opponent_archetype: '',
  result: 'win',
  notes: '',
  opponent_primary: null,
  opponent_secondary: null,
}

/**
 * Una sesión abierta: cabecera, récord, rondas, y el formulario para añadir la
 * siguiente.
 *
 * El récord NO se calcula aquí. Cada operación sobre una ronda devuelve la sesión
 * entera ya recalculada por el servidor, así que solo hay una implementación del
 * cálculo y no puede haber dos que discrepen.
 */
export default function SessionDetail({ sessionId, onBack }) {
  const [session, setSession] = useState(null)
  const [form, setForm] = useState(EMPTY_ROUND)
  // Qué RONDA se está corrigiendo, o null. Nombre explícito para no
  // confundirse con editingHeader, que es otra cosa.
  const [editingRound, setEditingRound] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  // Edición de la CABECERA. Las rondas no pasan por aquí: cada una se guarda al
  // añadirla, así que no hay estado pendiente que confirmar. Esto existe porque
  // hasta ahora la sesión quedaba congelada al crearla, y equivocarse de fecha o
  // de mazo no tenía arreglo.
  const [editingHeader, setEditingHeader] = useState(false)
  const [header, setHeader] = useState(null)
  const [decks, setDecks] = useState([])

  useEffect(() => {
    let active = true

    getSession(sessionId)
      .then((s) => active && setSession(s))
      .catch((err) => active && setError(err.message))

    return () => {
      active = false
    }
  }, [sessionId])

  // Los mazos hacen falta para poder corregir con cuál se jugó.
  useEffect(() => {
    let active = true
    listDecks()
      .then((d) => active && setDecks(d))
      .catch(() => {})
    return () => {
      active = false
    }
  }, [])

  function startEditHeader() {
    setHeader({
      name: session.name ?? '',
      played_at: session.played_at,
      session_type: session.session_type,
      notes: session.notes ?? '',
      deck_version_id: session.deck_version_id,
    })
    setEditingHeader(true)
  }

  async function saveHeader(event) {
    event.preventDefault()
    const ok = await mutate(() =>
      updateSession(sessionId, {
        ...header,
        name: header.name.trim() || null,
        notes: header.notes.trim() || null,
      }),
    )
    if (ok) setEditingHeader(false)
  }

  /** Envoltorio común: toda mutación devuelve la sesión entera y la reemplaza. */
  async function mutate(operation) {
    setBusy(true)
    setError(null)
    try {
      setSession(await operation())
      return true
    } catch (err) {
      setError(err.message)
      return false
    } finally {
      setBusy(false)
    }
  }

  async function handleAdd(event) {
    event.preventDefault()
    const payload = { ...form, notes: form.notes.trim() || null }

    const ok = await mutate(() =>
      editingRound === null
        ? addMatch(sessionId, payload)
        : updateMatch(sessionId, editingRound, payload),
    )

    if (ok) {
      setForm(EMPTY_ROUND)
      setEditingRound(null)
    }
  }

  function startEdit(match) {
    setEditingRound(match.round)
    setForm({
      opponent_archetype: match.opponent_archetype,
      result: match.result,
      notes: match.notes ?? '',
      opponent_primary: match.opponent_primary ?? null,
      opponent_secondary: match.opponent_secondary ?? null,
    })
  }

  function cancelEdit() {
    setEditingRound(null)
    setForm(EMPTY_ROUND)
  }

  if (error && !session) return <p className="error">{error}</p>
  if (!session) return <p>Cargando…</p>

  const { record } = session

  return (
    <div className="session-detail">
      <div className="builder-head">
        <button type="button" className="back" onClick={onBack}>
          ← Sesiones
        </button>
        <div className="session-head">
          <h2>{session.name || TYPE_LABEL[session.session_type]}</h2>
          <p className="subtitle">
            {session.played_at} · {TYPE_LABEL[session.session_type]} · {session.deck_name}{' '}
            <span className="vtag">v{session.deck_version}</span>
          </p>
          {session.notes && <p className="session-notes">{session.notes}</p>}
          {!editingHeader && (
            <button type="button" className="peek" onClick={startEditHeader}>
              editar sesión
            </button>
          )}
        </div>
      </div>

      {editingHeader && (
        <form onSubmit={saveHeader} className="match-form session-edit">
          <h3>Editar sesión</h3>

          <label>
            Fecha
            <input
              type="date"
              value={header.played_at}
              onChange={(e) => setHeader({ ...header, played_at: e.target.value })}
              required
            />
          </label>

          <label>
            Tipo
            <select
              value={header.session_type}
              onChange={(e) => setHeader({ ...header, session_type: e.target.value })}
            >
              {SESSION_TYPES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
          </label>

          <label>
            Mazo
            <select
              value={header.deck_version_id}
              onChange={(e) => setHeader({ ...header, deck_version_id: e.target.value })}
            >
              {/* La versión actual de la sesión puede no ser la actual del mazo
                  —jugaste con la v1 y hoy vas por la v3— así que se ofrece
                  explícitamente para no perderla al abrir el desplegable. */}
              <option value={session.deck_version_id}>
                {session.deck_name} (v{session.deck_version}) — actual
              </option>
              {decks
                .filter((d) => d.current_version_id !== session.deck_version_id)
                .map((d) => (
                  <option key={d.id} value={d.current_version_id}>
                    {d.name} (v{d.current_version})
                  </option>
                ))}
            </select>
          </label>

          <label>
            Nombre <span className="optional">opcional</span>
            <input
              type="text"
              value={header.name}
              onChange={(e) => setHeader({ ...header, name: e.target.value })}
              placeholder="League Cup Guadalajara"
            />
          </label>

          <label>
            Notas del evento <span className="optional">opcional</span>
            <textarea
              value={header.notes}
              onChange={(e) => setHeader({ ...header, notes: e.target.value })}
              rows={2}
              placeholder="Cómo fue el día, qué probaste…"
            />
          </label>

          <div className="round-form-actions">
            <button type="submit" disabled={busy}>
              {busy ? 'Guardando…' : 'Guardar sesión'}
            </button>
            <button type="button" className="secondary" onClick={() => setEditingHeader(false)}>
              Cancelar
            </button>
          </div>
        </form>
      )}

      <div className="record">
        <span className="record-figure">
          {record.wins}–{record.losses}–{record.ties}
        </span>
        <span className="record-label">
          {session.matches.length === 0
            ? 'sin rondas todavía'
            : `${session.matches.length} ronda${session.matches.length > 1 ? 's' : ''}`}
        </span>
      </div>

      {error && <p className="error">{error}</p>}

      <ol className="rounds">
        {session.matches.map((m) => (
          <li key={m.round} className={`round round--${m.result}`}>
            <span className="round-no">R{m.round}</span>
            <span className="round-arch">
              <PokemonPair
                primary={m.opponent_primary}
                secondary={m.opponent_secondary}
                size={26}
              />
              {m.opponent_archetype}
            </span>
            <span className="round-result">
              {RESULTS.find((r) => r.value === m.result)?.label}
            </span>
            <span className="round-actions">
              <button type="button" onClick={() => startEdit(m)} disabled={busy}>
                corregir
              </button>
              <button
                type="button"
                onClick={() => mutate(() => deleteMatch(sessionId, m.round))}
                disabled={busy}
              >
                borrar
              </button>
            </span>
            {m.notes && <p className="round-notes">{m.notes}</p>}
          </li>
        ))}
      </ol>

      <form onSubmit={handleAdd} className="match-form round-form">
        <h3>{editingRound === null ? `Ronda ${session.matches.length + 1}` : `Corregir ronda ${editingRound}`}</h3>

        <label>
          Mazo del rival
          <input
            type="text"
            value={form.opponent_archetype}
            onChange={(e) => setForm({ ...form, opponent_archetype: e.target.value })}
            placeholder="Gardevoir ex"
            required
          />
        </label>

        <label>
          Pokémon del rival <span className="optional">opcional</span>
          <span className="pkm-two">
            <PokemonPicker
              value={form.opponent_primary}
              onSelect={(p) => setForm({ ...form, opponent_primary: p })}
              placeholder="gardevoir"
            />
            <PokemonPicker
              value={form.opponent_secondary}
              onSelect={(p) => setForm({ ...form, opponent_secondary: p })}
              placeholder="segundo"
            />
          </span>
        </label>

        <label>
          Resultado
          <select
            value={form.result}
            onChange={(e) => setForm({ ...form, result: e.target.value })}
          >
            {RESULTS.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </select>
        </label>

        <label>
          Notas <span className="optional">opcional</span>
          <textarea
            value={form.notes}
            onChange={(e) => setForm({ ...form, notes: e.target.value })}
            rows={2}
            placeholder="Qué pasó, qué cambiarías…"
          />
        </label>

        <div className="round-form-actions">
          <button type="submit" disabled={busy}>
            {editingRound === null ? 'Añadir ronda' : 'Guardar corrección'}
          </button>
          {editingRound !== null && (
            <button type="button" className="secondary" onClick={cancelEdit}>
              Cancelar
            </button>
          )}
        </div>
      </form>
    </div>
  )
}
