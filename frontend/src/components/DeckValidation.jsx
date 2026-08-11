const DECK_SIZE = 60

/**
 * Estado de legalidad del mazo.
 *
 * La validación la calcula el servidor y llega ya hecha; este componente solo la
 * presenta. Duplicar las reglas en el cliente para «avisar antes» sería tener dos
 * fuentes de verdad que acabarían discrepando.
 */
export default function DeckValidation({ validation, pendingTotal }) {
  // `pendingTotal` llega cuando hay cambios sin guardar. En ese caso la
  // validación del servidor describe una lista que ya no es la que ves, así que
  // NO se puede seguir afirmando «mazo legal»: sería mentira en pantalla.
  //
  // Se muestra el total contado en el cliente —una suma, no una regla— y el
  // veredicto se sustituye por «sin comprobar». Recalcular aquí las reglas
  // completas daría dos fuentes de verdad que acabarían discrepando; contar
  // cartas no corre ese riesgo.
  const stale = pendingTotal !== null && pendingTotal !== undefined
  const total = stale ? pendingTotal : validation.total_cards
  const isLegal = !stale && validation.is_legal
  const violations = stale ? [] : validation.violations
  const pct = Math.min(100, Math.round((total / DECK_SIZE) * 100))

  return (
    <div className={`validation ${isLegal ? 'is-legal' : ''} ${stale ? 'is-stale' : ''}`}>
      <div className="counter">
        <span className="count">
          {total}
          <span className="of">/{DECK_SIZE}</span>
        </span>
        <span className="verdict">
          {stale ? 'Sin comprobar — guarda para validar' : isLegal ? 'Mazo legal' : 'Todavía no es legal'}
        </span>
      </div>

      {/* aria-hidden porque el número de arriba ya dice lo mismo a un lector
          de pantalla; la barra es refuerzo visual, no información nueva. */}
      <div className="bar" aria-hidden="true">
        <div className="bar-fill" style={{ width: `${pct}%` }} />
      </div>

      {violations.length > 0 && (
        <ul className="violations">
          {violations.map((v, i) => (
            <li key={`${v.code}-${i}`}>{v.message}</li>
          ))}
        </ul>
      )}
    </div>
  )
}
