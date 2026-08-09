import { useEffect, useState } from 'react'
import { getCard } from '../api/cards'

const CATEGORY_LABEL = {
  Pokemon: 'Pokémon',
  Trainer: 'Entrenador',
  Energy: 'Energía',
}

/**
 * Detalle de una carta.
 *
 * Existe como componente aparte por una razón concreta, no por gusto: el listado
 * de TCGdex solo devuelve id, nombre e imagen. Rareza, marca de regulación y
 * legalidad requieren una llamada por carta.
 *
 * Pedir eso para las 24 cartas de la rejilla sería el problema **N+1**: una
 * consulta para la lista, más una por elemento. Con ~150ms cada una, serían más
 * de tres segundos y 24 peticiones para datos que el usuario quizá no mire. Así
 * que el detalle se pide solo cuando elige una carta: una llamada, cuando hace
 * falta.
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
    // cardId en las dependencias: elegir otra carta vuelve a pedir el detalle.
  }, [cardId])

  return (
    <aside className="card-detail">
      <button type="button" className="close" onClick={onClose} aria-label="Cerrar">
        ×
      </button>

      {error && <p className="error">{error}</p>}
      {!card && !error && <p>Cargando…</p>}

      {card && (
        <>
          {card.image_url && <img src={card.image_url} alt={card.name} />}
          <h3>{card.name}</h3>

          <dl>
            <dt>Categoría</dt>
            <dd>{CATEGORY_LABEL[card.category] ?? card.category}</dd>

            <dt>Rareza</dt>
            <dd>{card.rarity ?? '—'}</dd>

            <dt>Marca de regulación</dt>
            <dd>{card.regulation_mark ?? '—'}</dd>

            <dt>Legalidad</dt>
            <dd>
              <span className={card.legal_standard ? 'legal' : 'illegal'}>
                Standard {card.legal_standard ? '✓' : '✗'}
              </span>{' '}
              <span className={card.legal_expanded ? 'legal' : 'illegal'}>
                Expanded {card.legal_expanded ? '✓' : '✗'}
              </span>
            </dd>
          </dl>

          {card.is_ace_spec && <p className="ace-spec">ACE SPEC — máximo 1 por mazo</p>}
        </>
      )}
    </aside>
  )
}
