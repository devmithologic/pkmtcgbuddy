import { useState } from 'react'
import DeckBuilder from './DeckBuilder'
import DeckStats from './DeckStats'
import { useT } from '../i18n/index.jsx'

/**
 * The open deck, with its two faces: building it and measuring it.
 *
 * It exists as a separate component so DeckBuilder doesn't carry the
 * navigation on top of the building. Each one fetches its own data: the
 * stats view doesn't need the decklist, and vice versa.
 */
export default function DeckScreen({ deckId, isNew = false, onBack }) {
  const t = useT()
  const [view, setView] = useState('build')

  return (
    <div className="deck-screen">
      <div className="deck-modes">
        <button
          type="button"
          className={view === 'build' ? 'active' : ''}
          onClick={() => setView('build')}
        >
          {t('deckScreen.list')}
        </button>
        <button
          type="button"
          className={view === 'stats' ? 'active' : ''}
          onClick={() => setView('stats')}
        >
          {t('deckScreen.stats')}
        </button>
      </div>

      {/* Conditional, not CSS: the hidden view unmounts and cancels its
          in-flight requests. */}
      {view === 'build' ? (
        <DeckBuilder deckId={deckId} isNew={isNew} onBack={onBack} />
      ) : (
        <>
          <button type="button" className="back" onClick={onBack}>
            {t('deckScreen.back')}
          </button>
          <DeckStats deckId={deckId} />
        </>
      )}
    </div>
  )
}
