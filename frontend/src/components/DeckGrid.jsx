import { useT } from '../i18n/index.jsx'

const GROUPS = [
  { key: 'Pokemon' },
  { key: 'Trainer' },
  { key: 'Energy' },
]

/**
 * The decklist as a grid of cards with the quantity overlaid.
 *
 * This is how lists are read in the real world — and how Limitless or PTCG
 * Live publish them — because a 60-card list is recognized by its artwork
 * long before it is by its names. In text mode you have to read twenty lines
 * to know whether you're missing the Poké Ball; here you see it.
 *
 * It groups by category because that's the structure a decklist has, not a
 * decoration. With `grouped={false}` everything comes out in a single grid:
 * that's the "Preview" view, for seeing the whole deck at once the way a
 * published list looks, without the headers cutting up the grid.
 *
 * `readOnly` mode is for looking at old versions, which are frozen: they're
 * rendered the same but without the quantity controls, because offering a
 * button that can't do anything is worse than not offering it.
 */
export default function DeckGrid({
  cards,
  onChangeQuantity,
  onRemove,
  readOnly = false,
  size = 'm',
  grouped = true,
}) {
  const t = useT()

  if (cards.length === 0) {
    return <p className="empty">{t('deckGrid.emptyList')}</p>
  }

  /** One cell: the card, its quantity and, when editable, its controls. */
  function cell(entry) {
    return (
      <li
        key={entry.card.id}
        className={entry.legal_in_format ? '' : 'is-illegal'}
        title={entry.card.name}
      >
        <div className="deck-card">
          {entry.card.image_url ? (
            <img src={entry.card.image_url} alt={entry.card.name} loading="lazy" />
          ) : (
            <span className="no-image">{entry.card.name}</span>
          )}

          {/* The quantity sits OVER the card, like in published lists: that
              way the deck's proportions read at a glance without scanning a
              column of numbers. */}
          <span className="qty-badge">{entry.quantity}</span>

          {/* "ACE" (not "ACE SPEC"): a corner badge, space-constrained, and this
              abbreviation was never localized even in the pre-anglicization
              Spanish app — see es-to-en-diff.txt, which has no entry for it. */}
          {entry.is_ace_spec && <span className="corner ace">ACE</span>}
          {!entry.legal_in_format && <span className="corner illegal">!</span>}
        </div>

        {!readOnly && (
          <div className="grid-controls">
            <button
              type="button"
              onClick={() => onChangeQuantity(entry.card.id, entry.quantity - 1)}
              aria-label={t('deckGrid.removeOneCard', { name: entry.card.name })}
            >
              −
            </button>
            <button
              type="button"
              onClick={() => onChangeQuantity(entry.card.id, entry.quantity + 1)}
              aria-label={t('deckGrid.addOneCard', { name: entry.card.name })}
            >
              +
            </button>
            <button
              type="button"
              className="remove"
              onClick={() => onRemove(entry.card.id)}
              aria-label={t('deckGrid.removeCard', { name: entry.card.name })}
            >
              ×
            </button>
          </div>
        )}

        <span className="grid-name">{entry.card.name}</span>
      </li>
    )
  }

  if (!grouped) {
    return (
      <ul className="deck-grid" data-size={size}>
        {cards.map(cell)}
      </ul>
    )
  }

  return (
    <div className="deck-grid-groups">
      {GROUPS.map(({ key }) => {
        const group = cards.filter((c) => c.category === key)
        if (group.length === 0) return null

        const count = group.reduce((sum, c) => sum + c.quantity, 0)

        return (
          <section key={key}>
            <h4>
              {t(`cardCategory.${key}`)} <span className="group-count">{count}</span>
            </h4>

            <ul className="deck-grid" data-size={size}>
              {group.map(cell)}
            </ul>
          </section>
        )
      })}
    </div>
  )
}
