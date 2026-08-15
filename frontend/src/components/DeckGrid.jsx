const GROUPS = [
  { key: 'Pokemon', label: 'Pokémon' },
  { key: 'Trainer', label: 'Entrenador' },
  { key: 'Energy', label: 'Energía' },
]

/**
 * La lista del mazo como rejilla de cartas con la cantidad encima.
 *
 * Es como se leen las listas en el mundo real —y como las publican Limitless o
 * PTCG Live— porque una lista de 60 cartas se reconoce por las ilustraciones
 * mucho antes que por los nombres. En modo texto tienes que leer veinte líneas
 * para saber si te falta el Poké Ball; aquí lo ves.
 *
 * Agrupa por categoría porque es la estructura que tiene una lista de mazo, no
 * una decoración. Con `grouped={false}` sale todo en una sola rejilla: es la
 * vista «Preview», para ver el mazo entero de golpe como se ve una lista
 * publicada, sin que las cabeceras corten la retícula.
 *
 * Modo `readOnly` para mirar versiones antiguas, que están congeladas: se pintan
 * igual pero sin los controles de cantidad, porque ofrecer un botón que no puede
 * hacer nada es peor que no ofrecerlo.
 */
export default function DeckGrid({
  cards,
  onChangeQuantity,
  onRemove,
  readOnly = false,
  size = 'm',
  grouped = true,
}) {
  if (cards.length === 0) {
    return <p className="empty">Esta lista está vacía.</p>
  }

  /** Una celda: la carta, su cantidad y, si se puede editar, sus controles. */
  function celda(entry) {
    return (
      <li
        key={entry.card.id}
        className={entry.legal_in_format ? '' : 'is-illegal'}
        title={entry.card.name}
      >
        <div className="deck-card">
          {entry.card.image_url ? (
            <img src={entry.card.image_url} alt={entry.card.name} loading="lazy" />
          ) : (
            <span className="no-image">{entry.card.name}</span>
          )}

          {/* La cantidad va SOBRE la carta, como en las listas publicadas: así
              se lee la proporción del mazo de un vistazo sin recorrer una
              columna de números. */}
          <span className="qty-badge">{entry.quantity}</span>

          {entry.is_ace_spec && <span className="corner ace">ACE</span>}
          {!entry.legal_in_format && <span className="corner illegal">!</span>}
        </div>

        {!readOnly && (
          <div className="grid-controls">
            <button
              type="button"
              onClick={() => onChangeQuantity(entry.card.id, entry.quantity - 1)}
              aria-label={`Quitar una copia de ${entry.card.name}`}
            >
              −
            </button>
            <button
              type="button"
              onClick={() => onChangeQuantity(entry.card.id, entry.quantity + 1)}
              aria-label={`Añadir una copia de ${entry.card.name}`}
            >
              +
            </button>
            <button
              type="button"
              className="remove"
              onClick={() => onRemove(entry.card.id)}
              aria-label={`Eliminar ${entry.card.name}`}
            >
              ×
            </button>
          </div>
        )}

        <span className="grid-name">{entry.card.name}</span>
      </li>
    )
  }

  if (!grouped) {
    return (
      <ul className="deck-grid" data-size={size}>
        {cards.map(celda)}
      </ul>
    )
  }

  return (
    <div className="deck-grid-groups">
      {GROUPS.map(({ key, label }) => {
        const group = cards.filter((c) => c.category === key)
        if (group.length === 0) return null

        const count = group.reduce((sum, c) => sum + c.quantity, 0)

        return (
          <section key={key}>
            <h4>
              {label} <span className="group-count">{count}</span>
            </h4>

            <ul className="deck-grid" data-size={size}>
              {group.map(celda)}
            </ul>
          </section>
        )
      })}
    </div>
  )
}
