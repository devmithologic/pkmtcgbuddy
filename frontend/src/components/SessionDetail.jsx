import { useEffect, useState } from 'react'
import { addMatch, deleteMatch, getSession, updateMatch } from '../api/sessions'
import { TYPE_LABEL } from '../sessionTypes'
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
  const [editing, setEditing] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    let active = true

    getSession(sessionId)
      .then((s) => active && setSession(s))
      .catch((err) => active && setError(err.message))

    return () => {
      active = false
    }
  }, [sessionId])

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
      editing === null
        ? addMatch(sessionId, payload)
        : updateMatch(sessionId, editing, payload),
    )

    if (ok) {
      setForm(EMPTY_ROUND)
      setEditing(null)
    }
  }

  function startEdit(match) {
    setEditing(match.round)
    setForm({
      opponent_archetype: match.opponent_archetype,
      result: match.result,
      notes: match.notes ?? '',
      opponent_primary: match.opponent_primary ?? null,
      opponent_secondary: match.opponent_secondary ?? null,
    })
  }

  function cancelEdit() {
    setEditing(null)
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
        <div>
          <h2>{session.name || TYPE_LABEL[session.session_type]}</h2>
          <p className="subtitle">
            {session.played_at} · {TYPE_LABEL[session.session_type]} · {session.deck_name}{' '}
            <span className="vtag">v{session.deck_version}</span>
          </p>
        </div>
      </div>

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
        <h3>{editing === null ? `Ronda ${session.matches.length + 1}` : `Corregir ronda ${editing}`}</h3>

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
            {editing === null ? 'Añadir ronda' : 'Guardar corrección'}
          </button>
          {editing !== null && (
            <button type="button" className="secondary" onClick={cancelEdit}>
              Cancelar
            </button>
          )}
        </div>
      </form>
    </div>
  )
}
