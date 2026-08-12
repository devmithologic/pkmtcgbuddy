import { useState } from 'react'
import DeckBuilder from './DeckBuilder'
import DeckStats from './DeckStats'

/**
 * El mazo abierto, con sus dos caras: construirlo y medirlo.
 *
 * Existe como componente aparte para que DeckBuilder no cargue con la
 * navegación además de con el armado. Cada uno pide sus propios datos: la vista
 * de estadísticas no necesita la lista de cartas, y al revés.
 */
export default function DeckScreen({ deckId, onBack }) {
  const [view, setView] = useState('build')

  return (
    <div className="deck-screen">
      <div className="deck-modes">
        <button
          type="button"
          className={view === 'build' ? 'active' : ''}
          onClick={() => setView('build')}
        >
          Lista
        </button>
        <button
          type="button"
          className={view === 'stats' ? 'active' : ''}
          onClick={() => setView('stats')}
        >
          Estadísticas
        </button>
      </div>

      {/* Condicional, no CSS: la vista oculta se desmonta y cancela sus
          peticiones en vuelo. */}
      {view === 'build' ? (
        <DeckBuilder deckId={deckId} onBack={onBack} />
      ) : (
        <>
          <button type="button" className="back" onClick={onBack}>
            ← Mazos
          </button>
          <DeckStats deckId={deckId} />
        </>
      )}
    </div>
  )
}
