import { useEffect, useState } from 'react'
import { listMatches } from './api/matches'
import CardSearch from './components/CardSearch'
import MatchForm from './components/MatchForm'
import MatchList from './components/MatchList'
import './App.css'

const TABS = [
  { id: 'matches', label: 'Partidas' },
  { id: 'cards', label: 'Cartas' },
]

export default function App() {
  const [tab, setTab] = useState('matches')

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
              onClick={() => setTab(t.id)}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </header>

      {/* Renderizado condicional, no CSS: la pestaña oculta se DESMONTA. Eso
          cancela sus peticiones en vuelo, gracias a las limpiezas de useEffect.
          Ocultarla con display:none la dejaría viva y consultando TCGdex. */}
      {tab === 'matches' ? <MatchesView /> : <CardSearch />}
    </main>
  )
}

function MatchesView() {
  const [matches, setMatches] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let active = true

    listMatches()
      .then((data) => {
        if (active) setMatches(data)
      })
      .catch((err) => {
        if (active) setError(err.message)
      })
      .finally(() => {
        if (active) setLoading(false)
      })

    return () => {
      active = false
    }
  }, [])

  function handleCreated(match) {
    setMatches((previous) => [match, ...previous])
  }

  return (
    <>
      <MatchForm onCreated={handleCreated} />

      <section>
        <h2>Partidas ({matches.length})</h2>
        {loading && <p>Cargando…</p>}
        {error && <p className="error">No se pudieron cargar las partidas: {error}</p>}
        {!loading && !error && <MatchList matches={matches} />}
      </section>
    </>
  )
}
