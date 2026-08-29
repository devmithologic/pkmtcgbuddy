import { useEffect, useState } from 'react'
import { searchPokemon } from '../api/pokemon'

const DEBOUNCE_MS = 250

/**
 * Pokémon search box. Returns the reference chosen through `onSelect`.
 *
 * It repeats CardSearch's technique — debounce plus AbortController — but not
 * the component: it searches a different resource, returns something
 * different, and renders differently. Reusing the pattern is correct; reusing
 * the component would have forced it to do two jobs.
 *
 * The debounce is shorter than the cards' (250 ms versus 350) because here
 * the query runs against 1025 local documents and responds in microseconds:
 * the delay exists only so it doesn't fire a request per keystroke.
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
        // Aborting is a deliberate cancellation, not a failure to display.
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
          <img src={value.icon_url} alt={value.name} width={32} height={32} />
          <span>{value.name}</span>
          <button type="button" onClick={() => onSelect(null)} aria-label={`Remove ${value.name}`}>
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
                {/* icon_url and not art_url on purpose: there are 20 of these
                    at once here. With HOME renders, each search would be
                    2.5 MB. */}
                <img src={p.icon_url} alt="" width={28} height={28} />
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
