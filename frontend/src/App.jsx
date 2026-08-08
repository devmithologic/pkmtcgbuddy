import { useEffect, useState } from 'react'
import { listMatches } from './api/matches'
import MatchForm from './components/MatchForm'
import MatchList from './components/MatchList'
import './App.css'

export default function App() {
  const [matches, setMatches] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  /**
   * Carga inicial.
   *
   * El array vacío de dependencias significa "ejecuta esto después del primer
   * render y no lo repitas". Sin él, el efecto correría tras *cada* render;
   * como setMatches provoca un render, sería un bucle infinito de peticiones.
   *
   * En desarrollo verás DOS peticiones en la pestaña Network. No es un bug:
   * StrictMode (en main.jsx) monta, desmonta y vuelve a montar cada componente a
   * propósito, para destapar efectos que no limpian lo que empiezan. En
   * producción ocurre una sola vez.
   */
  useEffect(() => {
    // Nos protegemos de actualizar el estado de un componente ya desmontado: si
    // el usuario navega mientras la petición viaja, la respuesta llega tarde y
    // React avisaría de una fuga de memoria.
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

    // La función que devuelve useEffect es su limpieza. Se ejecuta al desmontar
    // el componente, y también antes de cada re-ejecución del efecto.
    return () => {
      active = false
    }
  }, [])

  /**
   * El formulario avisa de que creó una partida y la añadimos al principio.
   *
   * Aprovechamos que el POST devuelve el objeto ya creado, con su id real. La
   * alternativa —volver a pedir la lista entera— gasta un viaje de red extra
   * para obtener algo que el servidor ya nos dio.
   */
  function handleCreated(match) {
    setMatches((previous) => [match, ...previous])
  }

  return (
    <main className="app">
      <header>
        <h1>pkmtcgbuddy</h1>
        <p className="subtitle">Registro de partidas</p>
      </header>

      <MatchForm onCreated={handleCreated} />

      <section>
        <h2>Partidas ({matches.length})</h2>
        {loading && <p>Cargando…</p>}
        {error && <p className="error">No se pudieron cargar las partidas: {error}</p>}
        {!loading && !error && <MatchList matches={matches} />}
      </section>
    </main>
  )
}
