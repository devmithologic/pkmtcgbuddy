const GROUPS = [
  { key: 'Pokemon', label: 'Pokémon' },
  { key: 'Trainer', label: 'Entrenador' },
  { key: 'Energy', label: 'Energía' },
]

/**
 * La lista del mazo, agrupada por categoría.
 *
 * Se agrupa así porque es como se leen y se escriben las listas en el juego real:
 * cuenta de Pokémon, de entrenadores y de energías. Ordenar alfabéticamente sin
 * agrupar sería más fácil de programar y menos útil de usar.
 *
 * Presentacional: no pide datos ni los modifica. Recibe la lista y dos callbacks.
 */
export default function DeckCardList({ cards, onChangeQuantity, onRemove }) {
  if (cards.length === 0) {
    return <p className="empty">El mazo está vacío. Busca cartas a la derecha para añadirlas.</p>
  }

  return (
    <div className="deck-groups">
      {GROUPS.map(({ key, label }) => {
        const group = cards.filter((c) => c.category === key)
        if (group.length === 0) return null

        const count = group.reduce((sum, c) => sum + c.quantity, 0)

        return (
          <section key={key} className="deck-group">
            <h4>
              {label} <span className="group-count">{count}</span>
            </h4>

            <ul>
              {group.map((entry) => (
                <li key={entry.card.id} className={entry.legal_in_format ? '' : 'illegal-row'}>
                  <div className="qty">
                    <button
                      type="button"
                      onClick={() => onChangeQuantity(entry.card.id, entry.quantity - 1)}
                      aria-label={`Quitar una copia de ${entry.card.name}`}
                    >
                      −
                    </button>
                    <span>{entry.quantity}</span>
                    <button
                      type="button"
                      onClick={() => onChangeQuantity(entry.card.id, entry.quantity + 1)}
                      aria-label={`Añadir una copia de ${entry.card.name}`}
                    >
                      +
                    </button>
                  </div>

                  <span className="deck-card-name">
                    {entry.card.name}
                    {entry.is_ace_spec && <span className="tag ace">ACE SPEC</span>}
                    {entry.is_basic_energy && <span className="tag basic">básica</span>}
                    {!entry.legal_in_format && <span className="tag illegal">ilegal</span>}
                  </span>

                  <button
                    type="button"
                    className="remove"
                    onClick={() => onRemove(entry.card.id)}
                    aria-label={`Eliminar ${entry.card.name} del mazo`}
                  >
                    ×
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )
      })}
    </div>
  )
}
