/**
 * Los dos sprites de un mazo, juntos.
 *
 * Presentacional puro y diminuto, pero extraído a su propio fichero porque
 * aparece en cinco sitios: cabecera del mazo, listado de mazos, cada ronda de
 * una sesión, el formulario de ronda y las estadísticas. Duplicarlo cinco veces
 * garantiza que acaben divergiendo.
 */
export default function PokemonPair({ primary, secondary, size = 32, label }) {
  if (!primary && !secondary) return null

  return (
    <span className="pkm-pair" style={{ '--pkm-size': `${size}px` }}>
      {[primary, secondary].filter(Boolean).map((p) => (
        <img
          key={p.dex_id}
          src={p.sprite_url}
          /* El alt lleva el nombre porque el sprite ES la información aquí, no
             decoración: sin él, un lector de pantalla no sabría contra qué mazo
             se jugó. */
          alt={p.name}
          title={p.name}
          width={size}
          height={size}
          loading="lazy"
        />
      ))}
      {label && <span className="pkm-label">{label}</span>}
    </span>
  )
}
