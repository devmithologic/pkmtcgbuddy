import { useEffect, useRef, useState } from 'react'
import { getCard } from '../api/cards'
import {
  createVersion,
  getDeck,
  getVersion,
  listVersions,
  exportDeck,
  saveDeckCards,
  updateDeck,
} from '../api/decks'
import CardSearch from './CardSearch'
import DeckCardList from './DeckCardList'
import DeckGrid from './DeckGrid'
import DeckValidation from './DeckValidation'
import PokemonPair from './PokemonPair'
import PokemonPicker from './PokemonPicker'

/**
 * Deck-building screen.
 *
 * Local state while you edit, explicit save with a button. Chosen over
 * autosave because it's simpler to reason about in this first pass: what you
 * see is what there is, and "saved" means one single thing.
 *
 * The server is the authority on validation. Every save returns the deck
 * already validated, so we never compute the rules here — duplicating them
 * on the client would give two sources of truth that would eventually
 * disagree.
 */
export default function DeckBuilder({ deckId, isNew = false, onBack }) {
  const [deck, setDeck] = useState(null)
  // The name is edited in place, so it needs its own state: the server's
  // copy only updates on blur, not on every keystroke.
  const [name, setName] = useState('')
  const [cards, setCards] = useState([])
  const [versions, setVersions] = useState([])
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  // 'grid' or 'list'. Grid is the default mode because a 60-card list is
  // recognized faster by the artwork than by the names.
  const [view, setView] = useState('grid')
  // Card size chosen by the user. Defaults to 'm', which lets the container
  // queries drive it: the grid already adapts on its own to its column's
  // width. This control exists for when you want to see them bigger than
  // the space suggests, or fit all 60 on screen at once.
  const [gridSize, setGridSize] = useState('m')
  // Old version being viewed, if any. Shown alongside the current one so
  // you can compare while editing, which is exactly what's missing when
  // you change cards: seeing where you came from.
  const [comparing, setComparing] = useState(null)
  // Makes the auto-focus happen ONCE. An input's ref callback runs on
  // every render, so without this flag every keystroke would reselect the
  // text and typing would be impossible.
  const enfocado = useRef(false)
  // Exported text, or null. Requested from the server instead of assembled
  // here: the format is defined by `deck_text.py`, and having a second
  // implementation on the client guarantees they'll eventually disagree.
  const [exported, setExported] = useState(null)

  // Initial load. The two requests go together because neither depends on
  // the other: in series they'd take twice as long for no reason.
  useEffect(() => {
    let active = true

    Promise.all([getDeck(deckId), listVersions(deckId)])
      .then(([d, v]) => {
        if (!active) return
        setDeck(d)
        setName(d.name)
        setCards(d.current_version.cards)
        setVersions(v)
      })
      .catch((err) => active && setError(err.message))

    return () => {
      active = false
    }
  }, [deckId])

  /**
   * Adds a card from the search box.
   *
   * The search box only returns id, name and image — no category or
   * legality, because the card listing doesn't include them. Those are
   * requested with getCard: one request per card picked, which at ~1ms
   * against Mongo is free, and avoids rendering the list with incomplete
   * data until the next save.
   */
  async function handlePick(summary) {
    const existing = cards.find((c) => c.card.id === summary.id)

    if (existing) {
      changeQuantity(summary.id, existing.quantity + 1)
      return
    }

    try {
      const full = await getCard(summary.id)
      setCards((previous) => {
        // The check goes INSIDE the updater, not against the closure's
        // `cards`. Milliseconds pass between the click and getCard's
        // response, and two quick clicks on the same card would both see a
        // list without it: it got added twice, with the same React key and
        // two entries for the same card_id on save.
        if (previous.some((c) => c.card.id === full.id)) {
          return previous.map((c) =>
            c.card.id === full.id ? { ...c, quantity: c.quantity + 1 } : c,
          )
        }
        return [
        ...previous,
        {
          quantity: 1,
          card: { id: full.id, name: full.name, image_url: full.image_url },
          category: full.category,
          is_ace_spec: full.is_ace_spec,
          is_basic_energy: full.is_basic_energy,
          legal_in_format:
            deck.deck_format === 'standard' ? full.legal_standard : full.legal_expanded,
        },
        ]
      })
      setDirty(true)
    } catch (err) {
      setError(err.message)
    }
  }

  /**
   * Changes one of the deck's two icons.
   *
   * Saved instantly, without going through "Save changes". This is
   * deliberate: that button saves the card LIST, and mixing two different
   * things under the same button would force explaining which one saves
   * what.
   */
  /**
   * Saves a change to the HEADER: name, format or icons.
   *
   * Kept apart from saving the card list, deliberately. The list
   * accumulates locally and is sent with a button, because adding a card is
   * one step of a long task; the header is loose data that applies
   * immediately, like renaming a row in the list. That's why this PATCH
   * doesn't touch `dirty`.
   */
  async function patchDeck(cambios) {
    try {
      setDeck(await updateDeck(deckId, cambios))
    } catch (err) {
      setError(err.message)
    }
  }

  const setPokemon = (slot, pokemon) => patchDeck({ [slot]: pokemon })

  async function exporta() {
    setError(null)
    try {
      setExported(await exportDeck(deckId))
    } catch (err) {
      setError(err.message)
    }
  }

  /** Saves the name on blur or Enter. Empty is not saved. */
  async function guardaNombre() {
    const limpio = name.trim()
    if (!limpio || limpio === deck.name) {
      setName(deck.name)
      return
    }
    await patchDeck({ name: limpio })
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

  /** Loads an old version to view it, or closes it if already open. */
  async function toggleCompare(version) {
    if (comparing?.id === version.id) {
      setComparing(null)
      return
    }
    try {
      setComparing(await getVersion(deckId, version.id))
    } catch (err) {
      setError(err.message)
    }
  }

  function removeCard(cardId) {
    setCards((previous) => previous.filter((c) => c.card.id !== cardId))
    setDirty(true)
  }

  async function handleSave() {
    setSaving(true)
    setError(null)

    try {
      // The server only cares about id and quantity; the rest is data it
      // will resolve itself when it responds.
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
   * Creates a new version by copying the current one.
   *
   * Saves first if there are pending changes: otherwise, the new version
   * would be born with the old list and the changes would be lost without
   * warning.
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
      {/* Everything that identifies the deck, plus the save actions, in the
          same row. The name used to be a fixed <h2> and save lived inside
          the left column, below the validation panel: with a 60-card list
          it fell off-screen exactly when there were unsaved changes. */}
      <div className="builder-head">
        <button type="button" className="back" onClick={onBack}>
          ← Mazos
        </button>

        <PokemonPair
          primary={deck.primary_pokemon}
          secondary={deck.secondary_pokemon}
          size={72}
          variant="art"
        />

        <div className="builder-id">
          <div className="builder-title">
            <input
              className="deck-title"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onBlur={guardaNombre}
              onKeyDown={(e) => {
                if (e.key === 'Enter') e.currentTarget.blur()
                if (e.key === 'Escape') setName(deck.name)
              }}
              aria-label="Nombre del mazo"
              /* A newly created deck is called "Mazo nuevo": focusing and
                 selecting lets you type over it without deleting it by
                 hand. */
              ref={(el) => {
                if (el && isNew && !enfocado.current) {
                  enfocado.current = true
                  el.focus()
                  el.select()
                }
              }}
            />

            <div className="builder-actions">
              <button type="button" onClick={handleSave} disabled={!dirty || saving}>
                {saving ? 'Guardando…' : dirty ? 'Guardar cambios' : 'Sin cambios'}
              </button>
              <button
                type="button"
                className="secondary"
                onClick={handleNewVersion}
                disabled={saving}
              >
                Nueva versión
              </button>
              <button type="button" className="secondary" onClick={exporta}>
                Exportar
              </button>
            </div>
          </div>

          <p className="subtitle builder-meta">
            <select
              value={deck.deck_format}
              onChange={(e) => patchDeck({ deck_format: e.target.value })}
              aria-label="Formato del mazo"
            >
              <option value="standard">Standard</option>
              <option value="expanded">Expanded</option>
            </select>
            · versión {deck.current_version.version} · {deck.current_version.message}
          </p>

          <div className="deck-pokemon">
            <PokemonPicker
              value={deck.primary_pokemon}
              onSelect={(p) => setPokemon('primary_pokemon', p)}
            />
            <PokemonPicker
              value={deck.secondary_pokemon}
              onSelect={(p) => setPokemon('secondary_pokemon', p)}
              placeholder="secundario"
            />
          </div>
        </div>
      </div>

      {error && <p className="error">{error}</p>}

      {exported !== null && (
        <div className="deck-export">
          <p className="hint">
            Lista en el formato de PTCG Live. Cópiala y pégala en cualquier constructor.
          </p>
          <textarea readOnly rows={12} value={exported} spellCheck={false} />
          <div className="builder-actions">
            <button type="button" onClick={() => navigator.clipboard?.writeText(exported)}>
              Copiar
            </button>
            <button type="button" className="secondary" onClick={() => setExported(null)}>
              Cerrar
            </button>
          </div>
        </div>
      )}

      <div className="builder-cols">
        <div className="builder-deck">
          {/* While there are unsaved changes, the locally counted total is
              passed in, so the panel doesn't keep claiming a 62-card deck
              is legal. */}
          <DeckValidation
            validation={deck.validation}
            pendingTotal={dirty ? cards.reduce((sum, c) => sum + c.quantity, 0) : null}
          />

          {dirty && <p className="hint">Hay cambios sin guardar.</p>}

          <div className="view-toggle">
            <button
              type="button"
              className={view === 'grid' ? 'active' : ''}
              onClick={() => setView('grid')}
            >
              Cartas
            </button>
            <button
              type="button"
              className={view === 'list' ? 'active' : ''}
              onClick={() => setView('list')}
            >
              Lista
            </button>
            {/* The whole deck at once, with no category headers breaking up
                the grid: it's how a published list is viewed. Read-only on
                purpose — the other two views are for editing, and offering
                those controls here would just repeat them under another
                name. */}
            <button
              type="button"
              className={view === 'preview' ? 'active' : ''}
              onClick={() => setView('preview')}
            >
              Preview
            </button>

            {view !== 'list' && (
              <span className="grid-size">
                {[
                  ['s', 'Cartas pequeñas'],
                  ['m', 'Cartas medianas'],
                  ['l', 'Cartas grandes'],
                ].map(([valor, titulo]) => (
                  <button
                    key={valor}
                    type="button"
                    className={gridSize === valor ? 'active' : ''}
                    onClick={() => setGridSize(valor)}
                    title={titulo}
                    aria-label={titulo}
                    aria-pressed={gridSize === valor}
                  >
                    {valor.toUpperCase()}
                  </button>
                ))}
              </span>
            )}
          </div>

          {view === 'list' ? (
            <DeckCardList cards={cards} onChangeQuantity={changeQuantity} onRemove={removeCard} />
          ) : (
            <DeckGrid
              cards={cards}
              onChangeQuantity={changeQuantity}
              onRemove={removeCard}
              size={gridSize}
              grouped={view === 'grid'}
              readOnly={view === 'preview'}
            />
          )}

          {comparing && (
            <section className="comparing">
              <h4>
                Consultando v{comparing.version} · {comparing.message}
                <button type="button" onClick={() => setComparing(null)}>
                  cerrar
                </button>
              </h4>
              <p className="hint">
                Solo lectura: las versiones anteriores están congeladas.
              </p>
              {/* readOnly removes the controls: offering a button that
                  can't do anything confuses more than it helps. */}
              <DeckGrid cards={comparing.cards} readOnly size={gridSize} />
            </section>
          )}

          {versions.length > 0 && (
            <section className="history">
              <h4>Historial</h4>
              <ul>
                {versions.map((v) => (
                  <li key={v.id} className={v.version === deck.current_version.version ? 'current' : ''}>
                    <span className="vnum">v{v.version}</span>
                    <span className="vmsg">{v.message}</span>
                    <span className="vcount">{v.total_cards} cartas</span>
                    {v.version !== deck.current_version.version && (
                      <button type="button" className="peek" onClick={() => toggleCompare(v)}>
                        {comparing?.id === v.id ? 'ocultar' : 'ver'}
                      </button>
                    )}
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
          {/* The same CardSearch from the Cards tab. With onPick present,
              clicking adds to the deck instead of opening the detail view. */}
          <CardSearch onPick={handlePick} defaultFormat={deck.deck_format} />
        </div>
      </div>
    </div>
  )
}
