import { useEffect, useState } from 'react'
import { createDeck, listDecks } from '../api/decks'
import PokemonPair from './PokemonPair'
import PokemonPicker from './PokemonPicker'

const EMPTY = { name: '', deck_format: 'standard', primary_pokemon: null, secondary_pokemon: null }

/** Listado de mazos y formulario de creación. */
export default function DeckList({ onOpen }) {
  const [decks, setDecks] = useState([])
  const [form, setForm] = useState(EMPTY)
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    let active = true

    listDecks()
      .then((data) => active && setDecks(data))
      .catch((err) => active && setError(err.message))
      .finally(() => active && setLoading(false))

    return () => {
      active = false
    }
  }, [])

  async function handleSubmit(event) {
    event.preventDefault()
    setCreating(true)
    setError(null)

    try {
      const deck = await createDeck(form)
      setForm(EMPTY)
      // Abrimos el mazo recién creado: crear un mazo vacío y quedarse en la
      // lista obligaría a un clic extra para hacer lo único que tiene sentido
      // a continuación.
      onOpen(deck.id)
    } catch (err) {
      setError(err.message)
    } finally {
      setCreating(false)
    }
  }

  return (
    <section>
      <form onSubmit={handleSubmit} className="match-form">
        <h2>Nuevo mazo</h2>

        <label>
          Nombre
          <input
            type="text"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="Mega Lucario"
            required
          />
        </label>

        <label>
          Formato
          <select
            value={form.deck_format}
            onChange={(e) => setForm({ ...form, deck_format: e.target.value })}
          >
            <option value="standard">Standard</option>
            <option value="expanded">Expanded</option>
          </select>
        </label>

        <label>
          Pokémon <span className="optional">opcional, identifica el mazo</span>
          <span className="pkm-two">
            <PokemonPicker
              value={form.primary_pokemon}
              onSelect={(p) => setForm({ ...form, primary_pokemon: p })}
            />
            <PokemonPicker
              value={form.secondary_pokemon}
              onSelect={(p) => setForm({ ...form, secondary_pokemon: p })}
              placeholder="dusknoir"
            />
          </span>
        </label>

        <button type="submit" disabled={creating}>
          {creating ? 'Creando…' : 'Crear mazo'}
        </button>
      </form>

      <h2>Mazos ({decks.length})</h2>
      {loading && <p>Cargando…</p>}
      {error && <p className="error">{error}</p>}

      {!loading && decks.length === 0 && (
        <p className="empty">Todavía no hay mazos.</p>
      )}

      <ul className="deck-list">
        {decks.map((deck) => (
          <li key={deck.id}>
            <button type="button" onClick={() => onOpen(deck.id)}>
              <PokemonPair
                primary={deck.primary_pokemon}
                secondary={deck.secondary_pokemon}
                size={28}
              />
              <span className="deck-name">{deck.name}</span>
              <span className="deck-meta">
                {deck.deck_format === 'standard' ? 'Standard' : 'Expanded'} · v
                {deck.current_version}
              </span>
              <span className={`deck-count ${deck.is_legal ? 'ok' : ''}`}>
                {deck.total_cards}/60
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}
