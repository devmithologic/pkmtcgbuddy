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

const VIEW_STORAGE_KEY = 'pkmtcgbuddy.deckView'

function savedView() {
  return localStorage.getItem(VIEW_STORAGE_KEY) === 'flat' ? 'flat' : 'folders'
}

/**
 * Decks and folders, navigated like a file explorer.
 *
 * The change from the previous version isn't cosmetic. Before, the WHOLE
 * tree was rendered expanded and the creation form always lived off to the
 * side; now only one folder is shown at a time and you navigate into it.
 * Two consequences worth having:
 *
 * - What you create is created WHERE YOU ARE. A folder selector in the
 *   form was asking for the same data twice: the navigation already says it.
 * - The "No folder" group disappears. It was never a folder, it was the
 *   rest; with navigation, the root already IS that place.
 */
export default function DeckList({ onOpen, currentId, setCurrentId }) {
  const [decks, setDecks] = useState([])
  const [folders, setFolders] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [view, setView] = useState(savedView)

  // `currentId` — where you are, null is the root — lives in App and not
  // here. When a deck opens, App unmounts this component to render the
  // builder, so local state was getting lost: you'd always land back on the
  // root instead of the folder you came from. That's the price of not
  // having a router; lifting the state one level up pays it without adding
  // a dependency.

  // In-place rename: {kind: 'folder'|'deck', id, name}.
  // Import screen: null when it's not open. Holds the pasted text and the
  // report of what couldn't be resolved.
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

  const byId = new Map(folders.map((f) => [f.id, f]))
  const flatFolders = flattenTree(buildTree(folders))

  /** Path from the root to the current folder, for the breadcrumb. */
  function getPath(id) {
    const path = []
    let current = id ? byId.get(id) : null
    while (current) {
      path.unshift(current)
      current = current.parent_id ? byId.get(current.parent_id) : null
    }
    return path
  }

  const path = getPath(currentId)
  const subfolders = folders.filter((f) => (f.parent_id ?? null) === currentId)
  const decksHere = decks.filter((d) => (d.folder_id ?? null) === currentId)

  function isDescendant(candidateId, ancestorId) {
    let current = byId.get(candidateId)
    while (current?.parent_id) {
      if (current.parent_id === ancestorId) return true
      current = byId.get(current.parent_id)
    }
    return false
  }

  function changeView(v) {
    setView(v)
    localStorage.setItem(VIEW_STORAGE_KEY, v)
  }

  async function withErrorHandling(action) {
    setError(null)
    try {
      await action()
      await reload()
    } catch (err) {
      setError(err.message)
    }
  }

  /**
   * Creates the deck and goes straight into the builder.
   *
   * No form beforehand: the name and format are edited inside, the same way
   * a folder is renamed in its row. The folder comes from where you are,
   * not from a dropdown — asking for it would be requesting the same data
   * twice.
   */
  async function createNewDeck() {
    setError(null)
    try {
      const deck = await createDeck({
        name: 'Mazo nuevo',
        deck_format: 'standard',
        folder_id: currentId,
      })
      // The second argument tells the builder it was just created, so it
      // focuses the name with the text selected.
      onOpen(deck.id, true)
    } catch (err) {
      setError(err.message)
    }
  }

  async function importList(event) {
    event.preventDefault()
    setError(null)
    setImporting((p) => ({ ...p, busy: true }))
    try {
      const r = await importDeck({
        text: importing.text,
        name: importing.name.trim() || null,
        folder_id: currentId,
      })
      // If EVERYTHING came in, there's nothing to report: the deck just
      // opens. If something got left out, the report is shown before
      // continuing — which is the whole point of having chosen "import what
      // resolves and say what didn't".
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
   * Creates the folder and leaves it ready to rename, like a desktop.
   *
   * It's created first with a placeholder name and edited afterward,
   * instead of asking for the name up front: this way the folder exists
   * from the first moment — you can see where it landed — and canceling
   * the rename leaves something, not nothing.
   */
  async function createNewFolder() {
    setError(null)
    try {
      const folder = await createFolder({ name: 'Carpeta nueva', parent_id: currentId })
      await reload()
      setRenaming({ kind: 'folder', id: folder.id, name: folder.name })
    } catch (err) {
      setError(err.message)
    }
  }

  async function saveName(event) {
    event.preventDefault()
    // Called from both onSubmit and onBlur. Escape cancels by setting
    // `renaming` to null, so a blur that arrives afterward would find
    // nothing to save.
    if (!renaming) return
    const { kind, id, name } = renaming
    const cleaned = name.trim()
    if (!cleaned) return
    await withErrorHandling(() =>
      kind === 'folder' ? updateFolder(id, { name: cleaned }) : updateDeck(id, { name: cleaned }),
    )
    setRenaming(null)
  }

  function moveTargets(item, kind) {
    const current = kind === 'folder' ? item.parent_id : item.folder_id
    return [
      ...flatFolders
        .filter(
          (f) =>
            f.id !== (kind === 'folder' ? item.id : null) &&
            f.id !== current &&
            !(kind === 'folder' && isDescendant(f.id, item.id)),
        )
        .map((f) => ({
          icon: '📂',
          label: `${'· '.repeat(f.depth)}Mover a ${f.name}`,
          onSelect: () =>
            withErrorHandling(() =>
              kind === 'folder'
                ? updateFolder(item.id, { parent_id: f.id })
                : updateDeck(item.id, { folder_id: f.id }),
            ),
        })),
      ...(current
        ? [
            {
              icon: '↩',
              label: 'Mover a la raíz',
              onSelect: () =>
                withErrorHandling(() =>
                  kind === 'folder'
                    ? updateFolder(item.id, { parent_id: null })
                    : updateDeck(item.id, { folder_id: null }),
                ),
            },
          ]
        : []),
    ]
  }

  const isRenaming = (item, kind) => renaming?.kind === kind && renaming.id === item.id

  /** A row's name, or the field to change it if it's being renamed. */
  function editableName(item, kind, className) {
    if (!isRenaming(item, kind)) return <span className={className}>{item.name}</span>

    return (
      <form className="rename" onSubmit={saveName}>
        <input
          type="text"
          value={renaming.name}
          onChange={(e) => setRenaming({ ...renaming, name: e.target.value })}
          onKeyDown={(e) => e.key === 'Escape' && setRenaming(null)}
          onBlur={saveName}
          aria-label="Nuevo nombre"
          /* eslint-disable-next-line jsx-a11y/no-autofocus -- the field
             appears from an explicit action and is the only thing to
             interact with. */
          autoFocus
          required
        />
      </form>
    )
  }

  /**
   * A row's body: a <button> normally, a <div> while renaming.
   *
   * It's not a whim of markup, it fixes a concrete bug: the text field used
   * to live INSIDE the row's button, and a <button>'s content model
   * forbids nesting interactive elements inside it. The browser doesn't
   * throw an error, it does something worse: it activates the button when
   * you press the SPACE BAR, no matter that focus was in the field. Typing
   * "Testing For Puebla" was impossible because the first space entered the
   * folder.
   *
   * Space and Enter activate a button by definition — that's how it's used
   * without a mouse — so there was nothing to intercept: as long as the
   * input was nested inside, the conflict was structural. The fix is not to
   * nest them.
   */
  function RowBody({ active, onOpen: open, children }) {
    if (!active) return <div className="row-main">{children}</div>
    return (
      <button type="button" className="row-main" onClick={open}>
        {children}
      </button>
    )
  }

  function folderRow(folder) {
    const deckCount = decks.filter((d) => d.folder_id === folder.id).length
    const childCount = folders.filter((f) => f.parent_id === folder.id).length

    return (
      <li key={`f-${folder.id}`} className="deck-row folder-row">
        <RowBody
          active={!isRenaming(folder, 'folder')}
          onOpen={() => {
            setCurrentId(folder.id)
            setCreating(false)
          }}
        >
          <span className="row-icon" aria-hidden="true">
            📁
          </span>
          {editableName(folder, 'folder', 'deck-name')}
          <span className="deck-meta">
            {[
              childCount && `${childCount} ${childCount === 1 ? 'carpeta' : 'carpetas'}`,
              `${deckCount} ${deckCount === 1 ? 'mazo' : 'mazos'}`,
            ]
              .filter(Boolean)
              .join(' · ')}
          </span>
          <span />
        </RowBody>

        {confirming?.id === folder.id ? (
          <span className="confirm-delete">
            ¿Borrar?
            <button
              type="button"
              onClick={async () => {
                await withErrorHandling(() => deleteFolder(folder.id))
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
            label={`Acciones de ${folder.name}`}
            actions={[
              {
                icon: '✏️',
                label: 'Renombrar',
                onSelect: () =>
                  setRenaming({ kind: 'folder', id: folder.id, name: folder.name }),
              },
              ...moveTargets(folder, 'folder'),
              {
                icon: '✕',
                label: 'Borrar',
                danger: true,
                onSelect: () => setConfirming({ kind: 'folder', id: folder.id }),
              },
            ]}
          />
        )}
      </li>
    )
  }

  function deckRow(deck) {
    return (
      <li key={`d-${deck.id}`} className="deck-row">
        <RowBody active={!isRenaming(deck, 'deck')} onOpen={() => onOpen(deck.id)}>
          {/* The slot always exists, whether the deck has icons or not:
              without it, decks with no Pokémon start their name 130 px
              earlier and the list ends up with a jagged left edge. */}
          <span className="pkm-slot">
            <PokemonPair
              primary={deck.primary_pokemon}
              secondary={deck.secondary_pokemon}
              size={44}
              variant="art"
            />
          </span>
          {editableName(deck, 'deck', 'deck-name')}
          <span className="deck-meta">
            {deck.deck_format === 'standard' ? 'Standard' : 'Expanded'} · v
            {deck.current_version}
          </span>
          <span className={`deck-count ${deck.is_legal ? 'ok' : ''}`}>
            {deck.total_cards}/60
          </span>
        </RowBody>

        {confirming?.id === deck.id ? (
          <span className="confirm-delete">
            ¿Borrar?
            <button
              type="button"
              onClick={async () => {
                await withErrorHandling(() => deleteDeck(deck.id))
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
              ...moveTargets(deck, 'deck'),
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
        {/* Breadcrumb. Each segment is a button: going up two levels is one
            click, not two. In the flat view there's nowhere to be, so it's
            not rendered. */}
        {view === 'folders' ? (
          <nav className="breadcrumb" aria-label="Ruta">
            <button
              type="button"
              onClick={() => setCurrentId(null)}
              disabled={currentId === null}
            >
              Mazos
            </button>
            {path.map((c) => (
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
                { icon: '📁', label: 'Nueva carpeta', onSelect: createNewFolder },
              { icon: '🃏', label: 'Nuevo mazo', onSelect: createNewDeck },
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
              onClick={() => changeView('folders')}
            >
              Carpetas
            </button>
            <button
              type="button"
              className={view === 'flat' ? 'active' : ''}
              onClick={() => changeView('flat')}
            >
              Todos
            </button>
          </div>
        </div>
      </div>

      {error && <p className="error">{error}</p>}
      {loading && <p>Cargando…</p>}

      {importing ? (
        <form className="deck-import" onSubmit={importList}>
          <h3>Importar lista</h3>
          <p className="hint">
            Pega una lista en el formato de PTCG Live o Limitless. Se creará un mazo en{' '}
            <strong>{path.length ? path[path.length - 1].name : 'Mazos'}</strong>.
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
              /* eslint-disable-next-line jsx-a11y/no-autofocus -- the
                 screen exists only to paste here. */
              autoFocus
              required
            />
          </label>

          {/* The report only appears when something got left out. It shows
              up BEFORE opening the deck, so the decision to continue is the
              user's, not a warning that gets lost. */}
          {importing.report && (
            <div className="import-report">
              <p>
                Importadas <strong>{importing.report.imported_cards}</strong> cartas. No se
                reconocieron {importing.report.unresolved.length}{' '}
                {importing.report.unresolved.length === 1 ? 'línea' : 'líneas'}:
              </p>
              <ul>
                {importing.report.unresolved.map((line) => (
                  <li key={line}>{line}</li>
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
        <ul className="deck-list">{decks.map(deckRow)}</ul>
      ) : (
        <>
          <ul className="deck-list">
            {subfolders.map(folderRow)}
            {decksHere.map(deckRow)}
          </ul>

          {!loading && subfolders.length === 0 && decksHere.length === 0 && (
            <p className="empty">
              {currentId ? 'Esta carpeta está vacía.' : 'Todavía no hay mazos.'}
            </p>
          )}
        </>
      )}
    </section>
  )
}
