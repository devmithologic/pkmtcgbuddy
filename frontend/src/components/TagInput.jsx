import { useState } from 'react'

/**
 * Tag input with suggestions drawn from the ones that already exist.
 *
 * The suggestions aren't a convenience: they're what prevents drift. If
 * reusing "gamesmart" is easier than typing it out, you don't end up with
 * "GameSmart" and "Game Smart" as separate tags. The server normalizes on
 * save regardless, but by then the user has already typed something they
 * don't recognize.
 *
 * No debounce or AbortController, unlike PokemonPicker: the suggestions
 * arrive already loaded via props. Filtering an in-memory array needs neither
 * delay nor cancellation.
 */
// The same cap the backend declares in SessionCreate/SessionUpdate. Without
// it, tag 11 is accepted on screen and saving fails with a raw validation
// message that doesn't say which control caused it.
const MAX_TAGS = 10

export default function TagInput({ value = [], suggestions = [], onChange }) {
  const [draft, setDraft] = useState('')

  const normalizada = draft.trim().toLowerCase()
  const coincidencias = normalizada
    ? suggestions
        .filter((s) => s.tag.includes(normalizada) && !value.includes(s.tag))
        .slice(0, 6)
    : []

  const lleno = value.length >= MAX_TAGS

  function add(tag) {
    const limpia = tag.trim().toLowerCase().replace(/\s+/g, ' ')
    if (limpia && !value.includes(limpia) && !lleno) onChange([...value, limpia])
    setDraft('')
  }

  function handleKey(event) {
    // Enter adds; comma too, because that's how lists get written.
    if (event.key === 'Enter' || event.key === ',') {
      event.preventDefault()
      add(draft)
    }
    // Backspace with the field empty deletes the last one: standard shortcut
    // for this kind of control, and it avoids having to aim at a tiny ×.
    if (event.key === 'Backspace' && !draft && value.length) {
      onChange(value.slice(0, -1))
    }
  }

  return (
    <div className="tag-input">
      <span className="tag-chips">
        {value.map((t) => (
          <span key={t} className="tag-chip">
            {t}
            <button type="button" onClick={() => onChange(value.filter((x) => x !== t))} aria-label={`Quitar ${t}`}>
              ×
            </button>
          </span>
        ))}
        <input
          type="text"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={handleKey}
          onBlur={() => draft && add(draft)}
          disabled={lleno}
          placeholder={
            lleno ? `máximo ${MAX_TAGS}` : value.length ? '' : 'gamesmart, preparación regional…'
          }
        />
      </span>

      {coincidencias.length > 0 && (
        <ul className="tag-suggestions">
          {coincidencias.map((s) => (
            <li key={s.tag}>
              <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => add(s.tag)}>
                {s.tag} <span className="tag-count">{s.sessions}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
