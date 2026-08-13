import { useEffect, useState } from 'react'
import { searchPokemon } from '../api/pokemon'

const DEBOUNCE_MS = 250

/**
 * Buscador de un Pokémon. Devuelve la referencia elegida por `onSelect`.
 *
 * Repite la técnica de CardSearch —debounce más AbortController— pero no el
 * componente: busca en otro recurso, devuelve otra cosa y se pinta distinto.
 * Reutilizar el patrón es correcto; reutilizar el componente habría sido
 * forzarlo a hacer dos trabajos.
 *
 * El debounce es más corto que el de las cartas (250 ms frente a 350) porque
 * aquí la consulta va contra 1025 documentos locales y responde en microsegundos:
 * el retardo solo existe para no lanzar una petición por tecla.
 */
export default function PokemonPicker({ value, onSelect, placeholder = 'dragapult' }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [open, setOpen] = useState(false)

  useEffect(() => {
    if (query.trim().length < 2) {
      setResults([])
      return
    }

    const controller = new AbortController()
    const timer = setTimeout(() => {
      searchPokemon(query.trim(), controller.signal)
        .then((data) => {
          setResults(data)
          setOpen(true)
        })
        // Abortar es cancelación deliberada, no un fallo que mostrar.
        .catch((err) => {
          if (err.name !== 'AbortError') setResults([])
        })
    }, DEBOUNCE_MS)

    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [query])

  function choose(pokemon) {
    onSelect(pokemon)
    setQuery('')
    setResults([])
    setOpen(false)
  }

  return (
    <div className="pkm-picker">
      {value ? (
        <span className="pkm-chosen">
          <img src={value.sprite_url} alt={value.name} width={32} height={32} />
          <span>{value.name}</span>
          <button type="button" onClick={() => onSelect(null)} aria-label={`Quitar ${value.name}`}>
            ×
          </button>
        </span>
      ) : (
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => results.length && setOpen(true)}
          placeholder={placeholder}
        />
      )}

      {open && results.length > 0 && !value && (
        <ul className="pkm-results">
          {results.map((p) => (
            <li key={p.dex_id}>
              <button type="button" onClick={() => choose(p)}>
                <img src={p.sprite_url} alt="" width={28} height={28} />
                <span>{p.name}</span>
                <span className="pkm-dex">#{p.dex_id}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
