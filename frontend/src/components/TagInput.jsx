import { useState } from 'react'
import { useT } from '../i18n/index.jsx'

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
  const t = useT()
  const [draft, setDraft] = useState('')

  const normalized = draft.trim().toLowerCase()
  const matches = normalized
    ? suggestions
        .filter((s) => s.tag.includes(normalized) && !value.includes(s.tag))
        .slice(0, 6)
    : []

  const full = value.length >= MAX_TAGS

  function add(tag) {
    const cleaned = tag.trim().toLowerCase().replace(/\s+/g, ' ')
    if (cleaned && !value.includes(cleaned) && !full) onChange([...value, cleaned])
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
        {value.map((tag) => (
          <span key={tag} className="tag-chip">
            {tag}
            <button
              type="button"
              onClick={() => onChange(value.filter((x) => x !== tag))}
              aria-label={t('tagInput.removeTag', { tag })}
            >
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
          disabled={full}
          placeholder={
            full
              ? t('tagInput.placeholderFull', { max: MAX_TAGS })
              : value.length
                ? ''
                : t('tagInput.placeholderEmpty')
          }
        />
      </span>

      {matches.length > 0 && (
        <ul className="tag-suggestions">
          {matches.map((s) => (
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
