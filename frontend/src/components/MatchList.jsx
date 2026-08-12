const RESULT_LABEL = {
  win: 'Victoria',
  loss: 'Derrota',
  tie: 'Empate',
}

/**
 * Lista de partidas.
 *
 * No tiene estado ni pide datos: recibe el array ya cargado por props y lo pinta.
 * Un componente así se llama *presentacional*, y tiene una ventaja práctica —
 * dado el mismo array, siempre produce lo mismo, así que se razona y se prueba
 * sin montar un servidor.
 */
export default function MatchList({ matches }) {
  if (matches.length === 0) {
    return <p className="empty">Todavía no hay partidas registradas.</p>
  }

  return (
    <ul className="match-list">
      {matches.map((match) => (
        // key le dice a React qué elemento es cuál entre dos renders, para poder
        // reordenar en vez de reconstruir la lista entera. Usamos el id del
        // backend; usar el índice del array es el error clásico, y se manifiesta
        // al insertar o borrar por el medio: React reutiliza el nodo equivocado.
        <li key={match.id} className={`match match--${match.result}`}>
          <span className="match__date">{match.played_at}</span>
          <span className="match__archetype">{match.opponent_archetype}</span>
          <span className="match__result">{RESULT_LABEL[match.result]}</span>
          {match.deck_name && (
            <span className="match__deck">
              {match.deck_name} <span className="vtag">v{match.deck_version}</span>
            </span>
          )}
          {match.notes && <p className="match__notes">{match.notes}</p>}
        </li>
      ))}
    </ul>
  )
}
