import { useT } from '../i18n/index.jsx'

const GROUPS = [
  { key: 'Pokemon' },
  { key: 'Trainer' },
  { key: 'Energy' },
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
  const t = useT()

  if (cards.length === 0) {
    return <p className="empty">{t('deckCardList.emptyDeck')}</p>
  }

  return (
    <div className="deck-groups">
      {GROUPS.map(({ key }) => {
        const group = cards.filter((c) => c.category === key)
        if (group.length === 0) return null

        const count = group.reduce((sum, c) => sum + c.quantity, 0)

        return (
          <section key={key} className="deck-group">
            <h4>
              {t(`cardCategory.${key}`)} <span className="group-count">{count}</span>
            </h4>

            <ul>
              {group.map((entry) => (
                <li key={entry.card.id} className={entry.legal_in_format ? '' : 'illegal-row'}>
                  <div className="qty">
                    <button
                      type="button"
                      onClick={() => onChangeQuantity(entry.card.id, entry.quantity - 1)}
                      aria-label={t('deckCardList.removeOneCard', { name: entry.card.name })}
                    >
                      −
                    </button>
                    <span>{entry.quantity}</span>
                    <button
                      type="button"
                      onClick={() => onChangeQuantity(entry.card.id, entry.quantity + 1)}
                      aria-label={t('deckCardList.addOneCard', { name: entry.card.name })}
                    >
                      +
                    </button>
                  </div>

                  <span className="deck-card-name">
                    {entry.card.name}
                    {entry.is_ace_spec && <span className="tag ace">{t('deckCardList.aceSpec')}</span>}
                    {entry.is_basic_energy && <span className="tag basic">{t('deckCardList.basic')}</span>}
                    {!entry.legal_in_format && <span className="tag illegal">{t('deckCardList.illegal')}</span>}
                  </span>

                  <button
                    type="button"
                    className="remove"
                    onClick={() => onRemove(entry.card.id)}
                    aria-label={t('deckCardList.removeDeck', { name: entry.card.name })}
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
