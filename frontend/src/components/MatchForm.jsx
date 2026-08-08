import { useState } from 'react'
import { createMatch } from '../api/matches'

/** Fecha de hoy en formato YYYY-MM-DD, que es lo que espera <input type="date">. */
function today() {
  return new Date().toISOString().slice(0, 10)
}

const EMPTY = {
  played_at: today(),
  opponent_archetype: '',
  result: 'win',
  notes: '',
}

/**
 * Formulario para registrar una partida.
 *
 * Recibe onCreated como prop: cuando el backend confirma la creación, se la pasa
 * al padre. Este componente no conoce la lista de partidas ni la modifica — solo
 * avisa de que ocurrió algo. Ese patrón se llama *lifting state up*: el estado
 * vive en el ancestro común y baja en forma de callbacks.
 */
export default function MatchForm({ onCreated }) {
  const [form, setForm] = useState(EMPTY)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  /**
   * Estos son *componentes controlados*: el valor del <input> no lo guarda el
   * DOM, lo guarda React en el estado, y el input solo lo refleja. Por eso cada
   * uno necesita value y onChange — sin onChange, el campo sería de solo lectura.
   */
  function handleChange(event) {
    const { name, value } = event.target
    setForm((previous) => ({ ...previous, [name]: value }))
  }

  async function handleSubmit(event) {
    // Sin esto el navegador recarga la página entera al enviar el formulario,
    // que es su comportamiento por defecto desde antes de que existiera React.
    event.preventDefault()

    setSubmitting(true)
    setError(null)

    try {
      const created = await createMatch({
        ...form,
        // El backend acepta null, no cadena vacía: "sin notas" y "notas vacías"
        // no son lo mismo.
        notes: form.notes.trim() || null,
      })
      onCreated(created)
      setForm({ ...EMPTY, played_at: form.played_at })
    } catch (err) {
      setError(err.message)
    } finally {
      // En finally, no dentro del try: si la petición falla, el botón tiene que
      // volver a habilitarse igualmente.
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="match-form">
      <h2>Registrar partida</h2>

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
        Mazo del rival
        <input
          type="text"
          name="opponent_archetype"
          value={form.opponent_archetype}
          onChange={handleChange}
          placeholder="Gardevoir ex"
          required
        />
      </label>

      <label>
        Resultado
        <select name="result" value={form.result} onChange={handleChange}>
          <option value="win">Victoria</option>
          <option value="loss">Derrota</option>
          <option value="tie">Empate</option>
        </select>
      </label>

      <label>
        Notas
        <textarea
          name="notes"
          value={form.notes}
          onChange={handleChange}
          rows={3}
          placeholder="Qué pasó, qué cambiarías…"
        />
      </label>

      <button type="submit" disabled={submitting}>
        {submitting ? 'Guardando…' : 'Guardar partida'}
      </button>

      {error && <p className="error">{error}</p>}
    </form>
  )
}
