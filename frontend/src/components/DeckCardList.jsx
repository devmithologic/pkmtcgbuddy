const GROUPS = [
  { key: 'Pokemon', label: 'Pokémon' },
  { key: 'Trainer', label: 'Trainer' },
  { key: 'Energy', label: 'Energy' },
]

/**
 * The deck's decklist, grouped by category.
 *
 * It's grouped this way because that's how lists are read and written in the
 * real game: a count of Pokémon, of Trainers, and of Energy. Sorting
 * alphabetically without grouping would be easier to code and less useful to
 * use.
 *
 * Presentational: it doesn't fetch data or modify it. It receives the list and
 * two callbacks.
 */
export default function DeckCardList({ cards, onChangeQuantity, onRemove }) {
  if (cards.length === 0) {
    return <p className="empty">The deck is empty. Search for cards on the right to add them.</p>
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
                      aria-label={`Remove one copy of ${entry.card.name}`}
                    >
                      −
                    </button>
                    <span>{entry.quantity}</span>
                    <button
                      type="button"
                      onClick={() => onChangeQuantity(entry.card.id, entry.quantity + 1)}
                      aria-label={`Add one copy of ${entry.card.name}`}
                    >
                      +
                    </button>
                  </div>

                  <span className="deck-card-name">
                    {entry.card.name}
                    {entry.is_ace_spec && <span className="tag ace">ACE SPEC</span>}
                    {entry.is_basic_energy && <span className="tag basic">basic</span>}
                    {!entry.legal_in_format && <span className="tag illegal">illegal</span>}
                  </span>

                  <button
                    type="button"
                    className="remove"
                    onClick={() => onRemove(entry.card.id)}
                    aria-label={`Remove ${entry.card.name} from deck`}
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
