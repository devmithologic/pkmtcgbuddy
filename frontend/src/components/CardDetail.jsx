import { useEffect, useState } from 'react'
import { getCard } from '../api/cards'

const CATEGORY_LABEL = {
  Pokemon: 'Pokémon',
  Trainer: 'Trainer',
  Energy: 'Energy',
}

/**
 * Detail of a card.
 *
 * It exists as a separate component for a concrete reason, not by taste: the
 * TCGdex listing only returns id, name and image. Rarity, regulation mark and
 * legality each require one call per card.
 *
 * Asking for that for the 24 cards in the grid would be the **N+1** problem:
 * one query for the list, plus one per item. At ~150ms each, that would be
 * over three seconds and 24 requests for data the user may never look at. So
 * the detail is only requested when they pick a card: one call, when it's
 * needed.
 */
export default function CardDetail({ cardId, onClose }) {
  const [card, setCard] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    const controller = new AbortController()
    setCard(null)
    setError(null)

    getCard(cardId, controller.signal)
      .then(setCard)
      .catch((err) => {
        if (err.name !== 'AbortError') setError(err.message)
      })

    return () => controller.abort()
    // cardId in the dependencies: picking another card fetches the detail again.
  }, [cardId])

  return (
    <aside className="card-detail">
      <button type="button" className="close" onClick={onClose} aria-label="Close">
        ×
      </button>

      {error && <p className="error">{error}</p>}
      {!card && !error && <p>Loading…</p>}

      {card && (
        <>
          {card.image_url && <img src={card.image_url} alt={card.name} />}
          <h3>{card.name}</h3>

          <dl>
            <dt>Category</dt>
            <dd>{CATEGORY_LABEL[card.category] ?? card.category}</dd>

            <dt>Rarity</dt>
            <dd>{card.rarity ?? '—'}</dd>

            <dt>Regulation mark</dt>
            <dd>{card.regulation_mark ?? '—'}</dd>

            <dt>Legality</dt>
            <dd>
              <span className={card.legal_standard ? 'legal' : 'illegal'}>
                Standard {card.legal_standard ? '✓' : '✗'}
              </span>{' '}
              <span className={card.legal_expanded ? 'legal' : 'illegal'}>
                Expanded {card.legal_expanded ? '✓' : '✗'}
              </span>
            </dd>
          </dl>

          {card.is_ace_spec && <p className="ace-spec">ACE SPEC — max 1 per deck</p>}
        </>
      )}
    </aside>
  )
}
