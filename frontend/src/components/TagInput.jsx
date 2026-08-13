import { useState } from 'react'

/**
 * Entrada de etiquetas con sugerencias de las que ya existen.
 *
 * Las sugerencias no son comodidad: son lo que evita la deriva. Si reusar
 * «gamesmart» es más fácil que teclearla, no acabas con «GameSmart» y
 * «Game Smart» como etiquetas distintas. El servidor normaliza igualmente al
 * guardar, pero para entonces el usuario ya escribió algo que no reconoce.
 *
 * Sin debounce ni AbortController, al revés que PokemonPicker: las sugerencias
 * llegan ya cargadas por props. Filtrar un array en memoria no necesita ni
 * retardo ni cancelación.
 */
// El mismo tope que declara el backend en SessionCreate/SessionUpdate. Sin él,
// la etiqueta 11 se acepta en pantalla y el guardado falla con un mensaje de
// validación en bruto que no dice qué control lo causó.
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
    // Enter añade; coma también, porque es como se escriben las listas.
    if (event.key === 'Enter' || event.key === ',') {
      event.preventDefault()
      add(draft)
    }
    // Retroceso con el campo vacío borra la última: atajo estándar en este
    // tipo de control, y evita tener que apuntar a una × diminuta.
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
