import { useState } from 'react'
import CardSearch from './components/CardSearch'
import DeckList from './components/DeckList'
import DeckScreen from './components/DeckScreen'
import SessionDetail from './components/SessionDetail'
import SessionList from './components/SessionList'
import { useLocale } from './i18n/index.jsx'
import './App.css'

const TABS = [
  { id: 'sessions', label: 'Sessions' },
  { id: 'decks', label: 'Decks' },
  { id: 'cards', label: 'Cards' },
]

// EN/ES are deliberately not run through t(): a switch that renames itself
// into the language you can't read is a switch you can't find. Same reason
// the aria-label below stays English-only.
function LocaleSwitch() {
  const { locale, setLocale } = useLocale()

  return (
    <div className="locale-switch" role="group" aria-label="Language">
      {['en', 'es'].map((code) => (
        <button
          key={code}
          type="button"
          className={locale === code ? 'active' : ''}
          aria-pressed={locale === code}
          onClick={() => setLocale(code)}
        >
          {code.toUpperCase()}
        </button>
      ))}
    </div>
  )
}

export default function App() {
  const [tab, setTab] = useState('sessions')
  // Which deck or session is open. null = the listing. This is navigation, and
  // with two levels it does not yet justify a router: two state variables say
  // the same thing without adding a dependency and a new mechanism.
  const [openDeckId, setOpenDeckId] = useState(null)
  // Whether the open deck was just created. The builder uses it to focus the
  // provisional name; it's kept apart from the id because they're two
  // different things.
  const [deckIsNew, setDeckIsNew] = useState(false)
  // Which folder the deck listing is standing in. Lives here because DeckList
  // unmounts when a deck opens, and coming back has to land where you were.
  const [deckFolderId, setDeckFolderId] = useState(null)
  const [openSessionId, setOpenSessionId] = useState(null)
  // Whether the session opens for editing. It's kept apart from the id, not
  // folded into it, because they're two different things: which one is open,
  // and in what mode.
  const [editSessionOnOpen, setEditSessionOnOpen] = useState(false)

  function openSession(id, editing = false) {
    setOpenSessionId(id)
    setEditSessionOnOpen(editing)
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
        <div className="header-top">
          <h1>pkmtcgbuddy</h1>
          <LocaleSwitch />
        </div>
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

      {/* Conditional rendering, not CSS: the hidden tab gets UNMOUNTED. That
          cancels its in-flight requests, thanks to the useEffect cleanups.
          Hiding it with display:none would leave it alive and querying. */}
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
            onOpen={(id, isNew = false) => {
              setOpenDeckId(id)
              setDeckIsNew(isNew)
            }}
          />
        ))}

      {tab === 'cards' && <CardSearch />}
    </main>
  )
}
