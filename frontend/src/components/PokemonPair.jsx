/**
 * The two sprites of a deck, together.
 *
 * Pure and tiny presentational component, but pulled out into its own file
 * because it appears in several places — deck listing, builder header and
 * every round of a session — and duplicating it guarantees they'd end up
 * diverging.
 *
 * `variant` picks between the two images the API gives for the same Pokémon:
 *
 *   icon   96×96 sprite, 1.2 KB. For dense contexts: a session's rounds.
 *   art    HOME render, 512×512, ~124 KB. For where the image is the heading
 *          and there are two or three, not twenty.
 *
 * It's a single prop because the decision belongs to the call site, not to
 * the component: the same pair of Pokémon is rendered large on the deck's
 * card and small on the round that was played with it.
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
          /* alt carries the name because the sprite IS the information here,
             not decoration: without it, a screen reader wouldn't know which
             deck was played against. */
          alt={p.name}
          title={p.name}
          /* Explicit width and height, not just CSS: they reserve the space
             before the image arrives. Without them, `loading="lazy"` collapses
             the row and pushes it on load — the same Cumulative Layout Shift
             that already broke the card grid. */
          width={size}
          height={size}
          loading="lazy"
        />
      ))}
      {label && <span className="pkm-label">{label}</span>}
    </span>
  )
}
