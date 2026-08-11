import { useEffect, useState } from 'react'
import { getCard } from '../api/cards'
import { createVersion, getDeck, listVersions, saveDeckCards } from '../api/decks'
import CardSearch from './CardSearch'
import DeckCardList from './DeckCardList'
import DeckValidation from './DeckValidation'

/**
 * Pantalla de armado de un mazo.
 *
 * Estado local mientras editas, guardado explícito con botón. Se eligió así
 * frente al autoguardado porque es más simple de razonar en esta primera pasada:
 * lo que ves es lo que hay, y «guardado» significa una sola cosa.
 *
 * El servidor es la autoridad sobre la validación. Cada guardado devuelve el mazo
 * ya validado, así que nunca calculamos reglas aquí — duplicarlas en el cliente
 * daría dos fuentes de verdad que acabarían discrepando.
 */
export default function DeckBuilder({ deckId, onBack }) {
  const [deck, setDeck] = useState(null)
  const [cards, setCards] = useState([])
  const [versions, setVersions] = useState([])
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  // Carga inicial. Las dos peticiones van juntas porque ninguna depende de la
  // otra: en serie tardarían el doble sin motivo.
  useEffect(() => {
    let active = true

    Promise.all([getDeck(deckId), listVersions(deckId)])
      .then(([d, v]) => {
        if (!active) return
        setDeck(d)
        setCards(d.current_version.cards)
        setVersions(v)
      })
      .catch((err) => active && setError(err.message))

    return () => {
      active = false
    }
  }, [deckId])

  /**
   * Añade una carta desde el buscador.
   *
   * El buscador solo devuelve id, nombre e imagen — no categoría ni legalidad,
   * porque el listado de cartas no las incluye. Se piden con getCard: una
   * petición por carta elegida, que a ~1ms contra Mongo es gratis, y evita
   * pintar la lista con datos incompletos hasta el siguiente guardado.
   */
  async function handlePick(summary) {
    const existing = cards.find((c) => c.card.id === summary.id)

    if (existing) {
      changeQuantity(summary.id, existing.quantity + 1)
      return
    }

    try {
      const full = await getCard(summary.id)
      setCards((previous) => [
        ...previous,
        {
          quantity: 1,
          card: { id: full.id, name: full.name, image_url: full.image_url },
          category: full.category,
          is_ace_spec: full.is_ace_spec,
          is_basic_energy: full.is_basic_energy,
          legal_in_format: deck.deck_format === 'standard' ? full.legal_standard : full.legal_expanded,
        },
      ])
      setDirty(true)
    } catch (err) {
      setError(err.message)
    }
  }

  function changeQuantity(cardId, quantity) {
    if (quantity < 1) {
      removeCard(cardId)
      return
    }
    setCards((previous) =>
      previous.map((c) => (c.card.id === cardId ? { ...c, quantity } : c)),
    )
    setDirty(true)
  }

  function removeCard(cardId) {
    setCards((previous) => previous.filter((c) => c.card.id !== cardId))
    setDirty(true)
  }

  async function handleSave() {
    setSaving(true)
    setError(null)

    try {
      // Al servidor solo le interesa id y cantidad; el resto son datos que él
      // mismo resolverá al responder.
      const payload = cards.map((c) => ({ card_id: c.card.id, quantity: c.quantity }))
      const updated = await saveDeckCards(deckId, payload)
      setDeck(updated)
      setCards(updated.current_version.cards)
      setDirty(false)
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  /**
   * Crea una versión nueva copiando la actual.
   *
   * Guarda antes si hay cambios pendientes: de lo contrario, la versión nueva
   * nacería con la lista vieja y los cambios se perderían sin aviso.
   */
  async function handleNewVersion() {
    const message = window.prompt('¿Qué cambia en esta versión?')
    if (!message) return

    setSaving(true)
    setError(null)

    try {
      if (dirty) {
        await saveDeckCards(
          deckId,
          cards.map((c) => ({ card_id: c.card.id, quantity: c.quantity })),
        )
      }
      const updated = await createVersion(deckId, message)
      setDeck(updated)
      setCards(updated.current_version.cards)
      setVersions(await listVersions(deckId))
      setDirty(false)
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  if (error && !deck) return <p className="error">{error}</p>
  if (!deck) return <p>Cargando…</p>

  return (
    <div className="deck-builder">
      <div className="builder-head">
        <button type="button" className="back" onClick={onBack}>
          ← Mazos
        </button>
        <div>
          <h2>{deck.name}</h2>
          <p className="subtitle">
            {deck.deck_format === 'standard' ? 'Standard' : 'Expanded'} · versión{' '}
            {deck.current_version.version} · {deck.current_version.message}
          </p>
        </div>
      </div>

      {error && <p className="error">{error}</p>}

      <div className="builder-cols">
        <div className="builder-deck">
          {/* Mientras haya cambios sin guardar se pasa el total contado en
              local, para que el panel no siga afirmando que un mazo de 62
              cartas es legal. */}
          <DeckValidation
            validation={deck.validation}
            pendingTotal={dirty ? cards.reduce((sum, c) => sum + c.quantity, 0) : null}
          />

          <div className="builder-actions">
            <button type="button" onClick={handleSave} disabled={!dirty || saving}>
              {saving ? 'Guardando…' : dirty ? 'Guardar cambios' : 'Sin cambios'}
            </button>
            <button type="button" className="secondary" onClick={handleNewVersion} disabled={saving}>
              Nueva versión
            </button>
          </div>

          {dirty && <p className="hint">Hay cambios sin guardar.</p>}

          <DeckCardList
            cards={cards}
            onChangeQuantity={changeQuantity}
            onRemove={removeCard}
          />

          {versions.length > 0 && (
            <section className="history">
              <h4>Historial</h4>
              <ul>
                {versions.map((v) => (
                  <li key={v.id} className={v.version === deck.current_version.version ? 'current' : ''}>
                    <span className="vnum">v{v.version}</span>
                    <span className="vmsg">{v.message}</span>
                    <span className="vcount">{v.total_cards} cartas</span>
                  </li>
                ))}
              </ul>
              <p className="hint">
                Solo la versión actual es editable. Las anteriores quedan congeladas para que las
                estadísticas atribuidas a ellas sigan siendo ciertas.
              </p>
            </section>
          )}
        </div>

        <div className="builder-search">
          {/* El mismo CardSearch de la pestaña Cartas. Con onPick presente,
              hacer clic añade al mazo en vez de abrir el detalle. */}
          <CardSearch onPick={handlePick} defaultFormat={deck.deck_format} />
        </div>
      </div>
    </div>
  )
}
