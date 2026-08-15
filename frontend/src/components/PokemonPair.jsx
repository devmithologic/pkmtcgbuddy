/**
 * Los dos sprites de un mazo, juntos.
 *
 * Presentacional puro y diminuto, pero extraído a su propio fichero porque
 * aparece en varios sitios —listado de mazos, cabecera del constructor y cada
 * ronda de una sesión— y duplicarlo garantiza que acaben divergiendo.
 *
 * `variant` elige entre las dos imágenes que da la API para el mismo Pokémon:
 *
 *   icon   sprite de 96×96 y 1.2 KB. Para lo denso: las rondas de una sesión.
 *   art    render de HOME, 512×512 y ~124 KB. Para donde la imagen es la
 *          cabecera y hay dos o tres, no veinte.
 *
 * Es un solo prop porque la decisión es del sitio que lo usa, no del componente:
 * el mismo par de Pokémon se pinta grande en la ficha del mazo y pequeño en la
 * ronda que se jugó con él.
 */
export default function PokemonPair({
  primary,
  secondary,
  size = 32,
  label,
  variant = 'icon',
}) {
  if (!primary && !secondary) return null

  return (
    <span className={`pkm-pair pkm-${variant}`} style={{ '--pkm-size': `${size}px` }}>
      {[primary, secondary].filter(Boolean).map((p) => (
        <img
          key={p.dex_id}
          src={variant === 'art' ? p.art_url : p.icon_url}
          /* El alt lleva el nombre porque el sprite ES la información aquí, no
             decoración: sin él, un lector de pantalla no sabría contra qué mazo
             se jugó. */
          alt={p.name}
          title={p.name}
          /* width y height explícitos, no solo el CSS: reservan el hueco antes
             de que la imagen llegue. Sin ellos, `loading="lazy"` colapsa la
             fila y la empuja al cargar — el mismo Cumulative Layout Shift que
             ya rompió la rejilla de cartas. */
          width={size}
          height={size}
          loading="lazy"
        />
      ))}
      {label && <span className="pkm-label">{label}</span>}
    </span>
  )
}
