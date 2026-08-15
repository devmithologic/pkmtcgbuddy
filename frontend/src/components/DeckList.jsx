import { useEffect, useState } from 'react'
import { createDeck, deleteDeck, importDeck, listDecks, updateDeck } from '../api/decks'
import {
  buildTree,
  createFolder,
  deleteFolder,
  flattenTree,
  listFolders,
  updateFolder,
} from '../api/folders'
import Menu from './Menu'
import PokemonPair from './PokemonPair'

const CLAVE_VISTA = 'pkmtcgbuddy.deckView'

function vistaGuardada() {
  return localStorage.getItem(CLAVE_VISTA) === 'flat' ? 'flat' : 'folders'
}

/**
 * Mazos y carpetas, navegando como en un explorador de archivos.
 *
 * El cambio respecto a la versión anterior no es estético. Antes se pintaba el
 * árbol ENTERO desplegado y el formulario de creación vivía siempre a un lado;
 * ahora se ve una sola carpeta cada vez y se entra en ella. Dos consecuencias
 * que valen la pena:
 *
 * - Lo que se crea, se crea DONDE ESTÁS. Un selector de carpeta en el
 *   formulario era pedir dos veces el mismo dato: la navegación ya lo dice.
 * - Desaparece el grupo «Sin carpeta». Nunca fue una carpeta, era el resto; con
 *   navegación, la raíz ya ES ese sitio.
 */
export default function DeckList({ onOpen, currentId, setCurrentId }) {
  const [decks, setDecks] = useState([])
  const [folders, setFolders] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [view, setView] = useState(vistaGuardada)

  // `currentId` —dónde estás, null es la raíz— vive en App y no aquí. Al abrir
  // un mazo, App desmonta este componente para pintar el constructor, así que un
  // estado local se perdía: volvías siempre a la raíz en vez de a la carpeta de
  // la que saliste. Es el precio de no tener router; subir el estado un nivel lo
  // paga sin añadir una dependencia.

  // Renombrado en el sitio: {kind: 'folder'|'deck', id, name}.
  // Pantalla de importar: null cuando no está abierta. Guarda el texto pegado y
  // el informe de lo que no se pudo resolver.
  const [importing, setImporting] = useState(null)
  const [renaming, setRenaming] = useState(null)
  const [confirming, setConfirming] = useState(null)

  async function reload() {
    const [d, f] = await Promise.all([listDecks(), listFolders()])
    setDecks(d)
    setFolders(f)
  }

  useEffect(() => {
    let active = true

    Promise.all([listDecks(), listFolders()])
      .then(([d, f]) => {
        if (!active) return
        setDecks(d)
        setFolders(f)
      })
      .catch((err) => active && setError(err.message))
      .finally(() => active && setLoading(false))

    return () => {
      active = false
    }
  }, [])

  const porId = new Map(folders.map((f) => [f.id, f]))
  const planas = flattenTree(buildTree(folders))

  /** Camino desde la raíz hasta la carpeta actual, para la miga de pan. */
  function ruta(id) {
    const camino = []
    let actual = id ? porId.get(id) : null
    while (actual) {
      camino.unshift(actual)
      actual = actual.parent_id ? porId.get(actual.parent_id) : null
    }
    return camino
  }

  const camino = ruta(currentId)
  const subcarpetas = folders.filter((f) => (f.parent_id ?? null) === currentId)
  const mazosAqui = decks.filter((d) => (d.folder_id ?? null) === currentId)

  function esDescendiente(candidato, ancestro) {
    let actual = porId.get(candidato)
    while (actual?.parent_id) {
      if (actual.parent_id === ancestro) return true
      actual = porId.get(actual.parent_id)
    }
    return false
  }

  function cambiaVista(v) {
    setView(v)
    localStorage.setItem(CLAVE_VISTA, v)
  }

  async function conError(accion) {
    setError(null)
    try {
      await accion()
      await reload()
    } catch (err) {
      setError(err.message)
    }
  }

  /**
   * Crea el mazo y entra directo al constructor.
   *
   * Sin formulario previo: el nombre y el formato se editan dentro, igual que
   * una carpeta se renombra en su fila. La carpeta sale de dónde estás, no de
   * un desplegable — preguntarlo sería pedir dos veces el mismo dato.
   */
  async function creaMazo() {
    setError(null)
    try {
      const deck = await createDeck({
        name: 'Mazo nuevo',
        deck_format: 'standard',
        folder_id: currentId,
      })
      // El segundo argumento le dice al constructor que es recién creado, para
      // que enfoque el nombre con el texto seleccionado.
      onOpen(deck.id, true)
    } catch (err) {
      setError(err.message)
    }
  }

  async function importaLista(event) {
    event.preventDefault()
    setError(null)
    setImporting((p) => ({ ...p, busy: true }))
    try {
      const r = await importDeck({
        text: importing.text,
        name: importing.name.trim() || null,
        folder_id: currentId,
      })
      // Si TODO entró, no hay nada que contar: se abre el mazo y ya. Si algo se
      // quedó fuera, se enseña el informe antes de continuar — que es el punto
      // de haber elegido «importar lo que resuelva y decir qué no».
      if (r.unresolved.length === 0) {
        setImporting(null)
        onOpen(r.deck.id)
      } else {
        setImporting({ ...importing, busy: false, report: r })
      }
    } catch (err) {
      setError(err.message)
      setImporting((p) => ({ ...p, busy: false }))
    }
  }

  /**
   * Crea la carpeta y la deja lista para renombrar, como un escritorio.
   *
   * Se crea primero con un nombre provisional y se edita después, en vez de
   * pedir el nombre antes: así la carpeta existe desde el primer momento —se ve
   * dónde ha caído— y cancelar el renombrado deja algo, no nada.
   */
  async function creaCarpeta() {
    setError(null)
    try {
      const carpeta = await createFolder({ name: 'Carpeta nueva', parent_id: currentId })
      await reload()
      setRenaming({ kind: 'folder', id: carpeta.id, name: carpeta.name })
    } catch (err) {
      setError(err.message)
    }
  }

  async function guardaNombre(event) {
    event.preventDefault()
    // Se llama desde onSubmit y desde onBlur. Escape cancela poniendo `renaming`
    // a null, así que un blur que llegue después encontraría nada que guardar.
    if (!renaming) return
    const { kind, id, name } = renaming
    const limpio = name.trim()
    if (!limpio) return
    await conError(() =>
      kind === 'folder' ? updateFolder(id, { name: limpio }) : updateDeck(id, { name: limpio }),
    )
    setRenaming(null)
  }

  function destinos(item, kind) {
    const actual = kind === 'folder' ? item.parent_id : item.folder_id
    return [
      ...planas
        .filter(
          (f) =>
            f.id !== (kind === 'folder' ? item.id : null) &&
            f.id !== actual &&
            !(kind === 'folder' && esDescendiente(f.id, item.id)),
        )
        .map((f) => ({
          icon: '📂',
          label: `${'· '.repeat(f.depth)}Mover a ${f.name}`,
          onSelect: () =>
            conError(() =>
              kind === 'folder'
                ? updateFolder(item.id, { parent_id: f.id })
                : updateDeck(item.id, { folder_id: f.id }),
            ),
        })),
      ...(actual
        ? [
            {
              icon: '↩',
              label: 'Mover a la raíz',
              onSelect: () =>
                conError(() =>
                  kind === 'folder'
                    ? updateFolder(item.id, { parent_id: null })
                    : updateDeck(item.id, { folder_id: null }),
                ),
            },
          ]
        : []),
    ]
  }

  const editando = (item, kind) => renaming?.kind === kind && renaming.id === item.id

  /** El nombre de una fila, o el campo para cambiarlo si se está renombrando. */
  function nombreEditable(item, kind, className) {
    if (!editando(item, kind)) return <span className={className}>{item.name}</span>

    return (
      <form className="rename" onSubmit={guardaNombre}>
        <input
          type="text"
          value={renaming.name}
          onChange={(e) => setRenaming({ ...renaming, name: e.target.value })}
          onKeyDown={(e) => e.key === 'Escape' && setRenaming(null)}
          onBlur={guardaNombre}
          aria-label="Nuevo nombre"
          /* eslint-disable-next-line jsx-a11y/no-autofocus -- el campo aparece
             por una acción explícita y es lo único con lo que interactuar. */
          autoFocus
          required
        />
      </form>
    )
  }

  /**
   * El cuerpo de una fila: un <button> normalmente, un <div> mientras se
   * renombra.
   *
   * No es un capricho de marcado, arregla un fallo concreto: el campo de texto
   * vivía DENTRO del botón de la fila, y el modelo de contenido de <button>
   * prohíbe meter elementos interactivos dentro. El navegador no da error, hace
   * algo peor: activa el botón al pulsar la BARRA ESPACIADORA, sin importar que
   * el foco estuviera en el campo. Escribir «Testing For Puebla» era imposible
   * porque el primer espacio entraba en la carpeta.
   *
   * Space y Enter activan un botón por definición —así se usa sin ratón— así
   * que no había nada que interceptar: mientras el input estuviera dentro, el
   * conflicto era estructural. La solución es no anidarlos.
   */
  function CuerpoFila({ activo, onOpen: abrir, children }) {
    if (!activo) return <div className="row-main">{children}</div>
    return (
      <button type="button" className="row-main" onClick={abrir}>
        {children}
      </button>
    )
  }

  function filaCarpeta(carpeta) {
    const dentro = decks.filter((d) => d.folder_id === carpeta.id).length
    const hijas = folders.filter((f) => f.parent_id === carpeta.id).length

    return (
      <li key={`f-${carpeta.id}`} className="deck-row folder-row">
        <CuerpoFila
          activo={!editando(carpeta, 'folder')}
          onOpen={() => {
            setCurrentId(carpeta.id)
            setCreating(false)
          }}
        >
          <span className="row-icon" aria-hidden="true">
            📁
          </span>
          {nombreEditable(carpeta, 'folder', 'deck-name')}
          <span className="deck-meta">
            {[
              hijas && `${hijas} ${hijas === 1 ? 'carpeta' : 'carpetas'}`,
              `${dentro} ${dentro === 1 ? 'mazo' : 'mazos'}`,
            ]
              .filter(Boolean)
              .join(' · ')}
          </span>
          <span />
        </CuerpoFila>

        {confirming?.id === carpeta.id ? (
          <span className="confirm-delete">
            ¿Borrar?
            <button
              type="button"
              onClick={async () => {
                await conError(() => deleteFolder(carpeta.id))
                setConfirming(null)
              }}
            >
              Sí
            </button>
            <button type="button" onClick={() => setConfirming(null)}>
              No
            </button>
          </span>
        ) : (
          <Menu
            label={`Acciones de ${carpeta.name}`}
            actions={[
              {
                icon: '✏️',
                label: 'Renombrar',
                onSelect: () =>
                  setRenaming({ kind: 'folder', id: carpeta.id, name: carpeta.name }),
              },
              ...destinos(carpeta, 'folder'),
              {
                icon: '✕',
                label: 'Borrar',
                danger: true,
                onSelect: () => setConfirming({ kind: 'folder', id: carpeta.id }),
              },
            ]}
          />
        )}
      </li>
    )
  }

  function filaMazo(deck) {
    return (
      <li key={`d-${deck.id}`} className="deck-row">
        <CuerpoFila activo={!editando(deck, 'deck')} onOpen={() => onOpen(deck.id)}>
          {/* El hueco existe siempre, tenga iconos el mazo o no: sin él, los
              mazos sin Pokémon empiezan su nombre 130 px antes y la lista queda
              con el borde izquierdo dentado. */}
          <span className="pkm-slot">
            <PokemonPair
              primary={deck.primary_pokemon}
              secondary={deck.secondary_pokemon}
              size={44}
              variant="art"
            />
          </span>
          {nombreEditable(deck, 'deck', 'deck-name')}
          <span className="deck-meta">
            {deck.deck_format === 'standard' ? 'Standard' : 'Expanded'} · v
            {deck.current_version}
          </span>
          <span className={`deck-count ${deck.is_legal ? 'ok' : ''}`}>
            {deck.total_cards}/60
          </span>
        </CuerpoFila>

        {confirming?.id === deck.id ? (
          <span className="confirm-delete">
            ¿Borrar?
            <button
              type="button"
              onClick={async () => {
                await conError(() => deleteDeck(deck.id))
                setConfirming(null)
              }}
            >
              Sí
            </button>
            <button type="button" onClick={() => setConfirming(null)}>
              No
            </button>
          </span>
        ) : (
          <Menu
            label={`Acciones de ${deck.name}`}
            actions={[
              {
                icon: '✏️',
                label: 'Renombrar',
                onSelect: () => setRenaming({ kind: 'deck', id: deck.id, name: deck.name }),
              },
              ...destinos(deck, 'deck'),
              {
                icon: '✕',
                label: 'Borrar',
                danger: true,
                onSelect: () => setConfirming({ kind: 'deck', id: deck.id }),
              },
            ]}
          />
        )}
      </li>
    )
  }


  return (
    <section className="decks-screen">
      <div className="deck-toolbar">
        {/* Miga de pan. Cada tramo es un botón: subir dos niveles es un clic, no
            dos. En la vista plana no hay dónde estar, así que no se pinta. */}
        {view === 'folders' ? (
          <nav className="breadcrumb" aria-label="Ruta">
            <button
              type="button"
              onClick={() => setCurrentId(null)}
              disabled={currentId === null}
            >
              Mazos
            </button>
            {camino.map((c) => (
              <span key={c.id}>
                <span className="sep" aria-hidden="true">
                  ›
                </span>
                <button
                  type="button"
                  onClick={() => setCurrentId(c.id)}
                  disabled={c.id === currentId}
                >
                  {c.name}
                </button>
              </span>
            ))}
          </nav>
        ) : (
          <h2 className="breadcrumb-title">Todos los mazos ({decks.length})</h2>
        )}

        <div className="toolbar-right">
          <Menu
              trigger="+ Nuevo"
              label="Crear"
              className="new-menu"
              align="left"
              actions={[
                { icon: '📁', label: 'Nueva carpeta', onSelect: creaCarpeta },
              { icon: '🃏', label: 'Nuevo mazo', onSelect: creaMazo },
              {
                icon: '📋',
                label: 'Importar lista',
                onSelect: () => setImporting({ text: '', name: '', busy: false, report: null }),
              },
            ]}
          />

          <div className="view-switch" role="group" aria-label="Cómo ver los mazos">
            <button
              type="button"
              className={view === 'folders' ? 'active' : ''}
              onClick={() => cambiaVista('folders')}
            >
              Carpetas
            </button>
            <button
              type="button"
              className={view === 'flat' ? 'active' : ''}
              onClick={() => cambiaVista('flat')}
            >
              Todos
            </button>
          </div>
        </div>
      </div>

      {error && <p className="error">{error}</p>}
      {loading && <p>Cargando…</p>}

      {importing ? (
        <form className="deck-import" onSubmit={importaLista}>
          <h3>Importar lista</h3>
          <p className="hint">
            Pega una lista en el formato de PTCG Live o Limitless. Se creará un mazo en{' '}
            <strong>{camino.length ? camino[camino.length - 1].name : 'Mazos'}</strong>.
          </p>

          <label>
            Nombre <span className="optional">opcional</span>
            <input
              type="text"
              value={importing.name}
              onChange={(e) => setImporting({ ...importing, name: e.target.value })}
              placeholder="Mega Lucario"
            />
          </label>

          <label>
            Lista
            <textarea
              value={importing.text}
              onChange={(e) => setImporting({ ...importing, text: e.target.value, report: null })}
              rows={16}
              spellCheck={false}
              placeholder={'Pokémon: 17\n3 Riolu PRE 50\n3 Mega Lucario ex MEG 77\n…'}
              /* eslint-disable-next-line jsx-a11y/no-autofocus -- la pantalla
                 existe solo para pegar aquí. */
              autoFocus
              required
            />
          </label>

          {/* El informe solo aparece cuando algo se quedó fuera. Sale ANTES de
              abrir el mazo, para que la decisión de continuar sea del usuario y
              no un aviso que se pierde. */}
          {importing.report && (
            <div className="import-report">
              <p>
                Importadas <strong>{importing.report.imported_cards}</strong> cartas. No se
                reconocieron {importing.report.unresolved.length}{' '}
                {importing.report.unresolved.length === 1 ? 'línea' : 'líneas'}:
              </p>
              <ul>
                {importing.report.unresolved.map((linea) => (
                  <li key={linea}>{linea}</li>
                ))}
              </ul>
              <p className="hint">
                Puede ser una errata, o una carta de un set que todavía no está sincronizado.
                Añádelas a mano en el constructor.
              </p>
            </div>
          )}

          <div className="builder-actions">
            {importing.report ? (
              <button type="button" onClick={() => onOpen(importing.report.deck.id)}>
                Abrir el mazo
              </button>
            ) : (
              <button type="submit" disabled={importing.busy}>
                {importing.busy ? 'Importando…' : 'Importar'}
              </button>
            )}
            <button type="button" className="secondary" onClick={() => setImporting(null)}>
              Cancelar
            </button>
          </div>
        </form>
      ) : view === 'flat' ? (
        <ul className="deck-list">{decks.map(filaMazo)}</ul>
      ) : (
        <>
          <ul className="deck-list">
            {subcarpetas.map(filaCarpeta)}
            {mazosAqui.map(filaMazo)}
          </ul>

          {!loading && subcarpetas.length === 0 && mazosAqui.length === 0 && (
            <p className="empty">
              {currentId ? 'Esta carpeta está vacía.' : 'Todavía no hay mazos.'}
            </p>
          )}
        </>
      )}
    </section>
  )
}
