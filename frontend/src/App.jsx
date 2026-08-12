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
  const [openSessionId, setOpenSessionId] = useState(null)

  function switchTab(id) {
    setTab(id)
    setOpenDeckId(null)
    setOpenSessionId(null)
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
          <SessionDetail sessionId={openSessionId} onBack={() => setOpenSessionId(null)} />
        ) : (
          <SessionList onOpen={setOpenSessionId} />
        ))}

      {tab === 'decks' &&
        (openDeckId ? (
          <DeckScreen deckId={openDeckId} onBack={() => setOpenDeckId(null)} />
        ) : (
          <DeckList onOpen={setOpenDeckId} />
        ))}

      {tab === 'cards' && <CardSearch />}
    </main>
  )
}
