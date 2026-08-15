import { useState } from 'react'
import CardSearch from './components/CardSearch'
import DeckList from './components/DeckList'
import DeckScreen from './components/DeckScreen'
import SessionDetail from './components/SessionDetail'
import SessionList from './components/SessionList'
import './App.css'

const TABS = [
  { id: 'sessions', label: 'Sesiones' },
  { id: 'decks', label: 'Mazos' },
  { id: 'cards', label: 'Cartas' },
]

export default function App() {
  const [tab, setTab] = useState('sessions')
  // Qué mazo o sesión está abierto. null = el listado. Es navegación, y con dos
  // niveles no justifica todavía un router: dos variables de estado dicen lo
  // mismo sin añadir una dependencia y un mecanismo nuevo.
  const [openDeckId, setOpenDeckId] = useState(null)
  // Si el mazo abierto se acaba de crear. Lo usa el constructor para enfocar el
  // nombre provisional; va aparte del id porque son dos cosas distintas.
  const [deckIsNew, setDeckIsNew] = useState(false)
  // En qué carpeta está parado el listado de mazos. Vive aquí porque DeckList se
  // desmonta al abrir un mazo, y al volver hay que aterrizar donde estabas.
  const [deckFolderId, setDeckFolderId] = useState(null)
  const [openSessionId, setOpenSessionId] = useState(null)
  // Si la sesión se abre para editarla. Va aparte del id y no dentro de él
  // porque son dos cosas distintas: cuál está abierta, y en qué modo.
  const [editSessionOnOpen, setEditSessionOnOpen] = useState(false)

  function openSession(id, editar = false) {
    setOpenSessionId(id)
    setEditSessionOnOpen(editar)
  }

  function switchTab(id) {
    setTab(id)
    setOpenDeckId(null)
    setDeckIsNew(false)
    setOpenSessionId(null)
    setEditSessionOnOpen(false)
  }

  return (
    <main className="app">
      <header>
        <h1>pkmtcgbuddy</h1>
        <nav className="tabs">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              className={tab === t.id ? 'active' : ''}
              onClick={() => switchTab(t.id)}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </header>

      {/* Renderizado condicional, no CSS: la pestaña oculta se DESMONTA. Eso
          cancela sus peticiones en vuelo, gracias a las limpiezas de useEffect.
          Ocultarla con display:none la dejaría viva y consultando. */}
      {tab === 'sessions' &&
        (openSessionId ? (
          <SessionDetail
            sessionId={openSessionId}
            startEditing={editSessionOnOpen}
            onBack={() => openSession(null)}
          />
        ) : (
          <SessionList onOpen={openSession} />
        ))}

      {tab === 'decks' &&
        (openDeckId ? (
          <DeckScreen
            deckId={openDeckId}
            isNew={deckIsNew}
            onBack={() => {
              setOpenDeckId(null)
              setDeckIsNew(false)
            }}
          />
        ) : (
          <DeckList
            currentId={deckFolderId}
            setCurrentId={setDeckFolderId}
            onOpen={(id, nuevo = false) => {
              setOpenDeckId(id)
              setDeckIsNew(nuevo)
            }}
          />
        ))}

      {tab === 'cards' && <CardSearch />}
    </main>
  )
}
