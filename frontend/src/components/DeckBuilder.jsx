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
export default function DeckBuilder({ deckId, isNew = false, onBack }) {
  const [deck, setDeck] = useState(null)
  // El nombre se edita en el sitio, así que necesita su propio estado: el del
  // servidor solo se actualiza al salir del campo, no en cada tecla.
  const [name, setName] = useState('')
  const [cards, setCards] = useState([])
  const [versions, setVersions] = useState([])
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  // 'grid' o 'list'. La rejilla es el modo por defecto porque una lista de 60
  // cartas se reconoce antes por las ilustraciones que por los nombres.
  const [view, setView] = useState('grid')
  // Tamaño de carta elegido por el usuario. Por defecto 'm', que deja mandar a
  // las container queries: la rejilla ya se adapta sola al ancho de su columna.
  // Este control existe para cuando quieres verlas más grandes de lo que el
  // hueco sugiere, o meter las 60 en pantalla de golpe.
  const [gridSize, setGridSize] = useState('m')
  // Versión antigua que se está consultando, si hay alguna. Se muestra al lado
  // de la actual para poder comparar mientras editas, que es justo lo que falta
  // cuando cambias cartas: ver de dónde vienes.
  const [comparing, setComparing] = useState(null)
  // Que el foco automático ocurra UNA vez. El ref de un input se ejecuta en cada
  // render, así que sin esta marca cada tecla volvería a seleccionar el texto y
  // escribir sería imposible.
  const enfocado = useRef(false)
  // Texto exportado, o null. Se pide al servidor en vez de componerlo aquí: el
  // formato lo define `deck_text.py`, y tener una segunda implementación en el
  // cliente garantiza que en algún momento discrepen.
  const [exported, setExported] = useState(null)

  // Carga inicial. Las dos peticiones van juntas porque ninguna depende de la
  // otra: en serie tardarían el doble sin motivo.
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
      setCards((previous) => {
        // La comprobación va DENTRO del actualizador, no contra el `cards` del
        // cierre. Entre el clic y la respuesta de getCard pasan milisegundos, y
        // dos clics rápidos en la misma carta veían ambos una lista sin ella:
        // se añadía dos veces, con la misma key de React y dos entradas del
        // mismo card_id al guardar.
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
   * Cambia uno de los dos iconos del mazo.
   *
   * Se guarda al instante, sin pasar por «Guardar cambios». Es deliberado: ese
   * botón guarda la LISTA de cartas, y mezclar dos cosas distintas bajo el mismo
   * botón obligaría a explicar cuál guarda qué.
   */
  /**
   * Guarda un cambio de la CABECERA: nombre, formato o iconos.
   *
   * Va aparte del guardado de la lista de cartas y es deliberado. La lista se
   * acumula en local y se manda con un botón, porque añadir una carta es un
   * paso de un trabajo largo; la cabecera son datos sueltos que se aplican al
   * momento, como el renombrado de una fila del listado. Por eso este PATCH no
   * toca `dirty`.
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

  /** Guarda el nombre al salir del campo o con Enter. Vacío no se guarda. */
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

  /** Carga una versión antigua para consultarla, o la cierra si ya está abierta. */
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
      {/* Todo lo que identifica al mazo, y las acciones de guardar, en la misma
          fila. Antes el nombre era un <h2> fijo y guardar vivía dentro de la
          columna izquierda, por debajo del panel de validación: con una lista de
          60 cartas quedaba fuera de pantalla justo cuando había cambios sin
          guardar. */}
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
              /* Un mazo recién creado se llama «Mazo nuevo»: enfocar y
                 seleccionar deja escribir encima sin borrar a mano. */
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
          {/* Mientras haya cambios sin guardar se pasa el total contado en
              local, para que el panel no siga afirmando que un mazo de 62
              cartas es legal. */}
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
            {/* El mazo entero de golpe, sin cabeceras de categoría cortando la
                retícula: es cómo se mira una lista publicada. Va en solo
                lectura a propósito — para editar están las otras dos, y ofrecer
                los controles aquí sería repetirlas con otro nombre. */}
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
              {/* readOnly quita los controles: ofrecer un botón que no puede
                  hacer nada confunde más que ayudar. */}
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
          {/* El mismo CardSearch de la pestaña Cartas. Con onPick presente,
              hacer clic añade al mazo en vez de abrir el detalle. */}
          <CardSearch onPick={handlePick} defaultFormat={deck.deck_format} />
        </div>
      </div>
    </div>
  )
}
