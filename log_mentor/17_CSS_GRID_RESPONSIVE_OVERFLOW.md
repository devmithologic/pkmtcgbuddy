# CSS Grid: Responsive Columns with Minimum Zero

> **Stack:** CSS · **Introduced in:** Two-column layouts · **Date:** 2026-08-15

## Definition

**`minmax(0, <size>)` in CSS Grid** is a column sizing function that sets a minimum width of zero, allowing the column to shrink below its content. Without the zero minimum, a column widens itself to fit its contents, breaking the grid and overflowing the viewport. This is the most common CSS Grid trap and affects every use case where content might not fit: long text, overflowing tables, nested grids.

## Why it exists

CSS Grid's default behavior for columns is `grid-template-columns: auto 1fr` — the first column takes what it needs, the second takes what remains. When a child doesn't fit:

```css
.grid {
  display: grid;
  grid-template-columns: auto 1fr;  /* The trap */
  gap: 1rem;
}
```

If the first column's content is wider than space permits — a long word, an unbreakable URL, a nested grid — the entire grid expands and overflows the viewport. The first column never shrinks because `auto` means "give me what I need", and it didn't negotiate with the available width.

The fix is to tell the column "you can shrink to zero":

```css
.grid {
  display: grid;
  grid-template-columns: minmax(0, auto) 1fr;  /* Allows first column to shrink */
}
```

Now when content overflows, the column shrinks, and its children are forced to wrap or handle overflow themselves (scrolling, ellipsis, smaller text). The grid stays inside the viewport.

## How it works

`minmax(min, max)` in a track size accepts two arguments:

- **min**: The shrinking limit. `0` means "shrink to nothing if needed"; `min-content` means "shrink only to the smallest unbreakable element".
- **max**: The growth limit. `1fr` means "take a fraction of remaining space"; `auto` means "grow to fit content".

When the grid lays out:

1. Each column is assigned its track size (e.g., `minmax(0, 1fr)`).
2. Content flows into columns. If content overflows a child, the child is responsible: it scrolls, wraps, clips, or applies text-overflow.
3. The column itself never widens beyond its track size to accommodate content.

Without the `0` minimum, a column defined as `minmax(auto, 1fr)` will grow beyond `1fr` if its content demands it — breaking the constraint and overflowing the grid.

## In this project

**Two-column layouts** (`frontend/src/App.css`):
```css
.screen-split {
  display: grid;
  /* Both columns can shrink to zero if needed; second takes remaining space */
  grid-template-columns: minmax(0, var(--measure)) minmax(0, 1fr);
  gap: var(--gap-6);
  align-items: start;
}

.screen-split--end {
  /* Same grid, columns in reverse order for different semantic flow */
  grid-template-columns: minmax(0, 1fr) minmax(0, var(--measure));
}

/* At narrow widths, stack into one column */
@media (max-width: 60rem) {
  .screen-split,
  .screen-split--end {
    grid-template-columns: minmax(0, 1fr);
  }
}
```

Used for:
- Session list (actions form on left, session rows on right)
- Session detail (matched rounds on left, "add round" form on right)
- Deck list originally, now single-column since the form moved away

**Nested content** (`frontend/src/components/SessionDetail.jsx`):
```jsx
// The form is a child of .screen-split
<div className="screen-split">
  <div className="pane">
    {/* Tall list of matches */}
  </div>
  
  <form className="match-form">
    {/* Form fields with labels */}
  </form>
</div>
```

The form is in a `minmax(0, var(--measure))` column, so if its fields overflow (a label with long text, a poorly wrapped field), the form itself shrinks, and text wrapping handles the rest. Without `minmax(0, ...)`, the form would expand the column beyond `var(--measure)` and break the two-column layout.

**Content column** (`frontend/src/App.css`):
```css
.pane {
  display: flex;
  flex-direction: column;
  /* min-width: 0 on a flex child inside a grid prevents text overflow
     in the same way minmax(0, ...) prevents it on the grid itself */
  min-width: 0;
}

.pane > h2:first-child {
  margin-top: 0;
}
```

The `.pane` is the second column's flex container. It sets `min-width: 0` so its children (a card grid, a list) can shrink and handle overflow. Without it, the nested flex would push the grid column wider.

## Gotchas

**minmax(0, ...) is not the only fix.**  Other valid approaches:

- `overflow-wrap: break-word` on the overflowing element (forces wrapping instead of shrinking).
- `word-break: break-all` (more aggressive).
- `text-overflow: ellipsis` with `overflow: hidden` (truncates with dots).
- Nested grid with `minmax(0, 1fr)` on its own columns (shrinking propagates down).

Choose based on content type: text wraps, very long URLs break, numbers truncate.

**min-width: 0 on flex children does the same thing.** A flex column inside a grid cell needs `min-width: 0` to shrink its nested flex items the same way a grid needs `minmax(0, ...)`. Both tell their children "I can be smaller than your content".

**This does not solve all overflow problems.** A table with many columns or an `<pre>` block still overflows. Use `overflow-x: auto` on the container instead.

```css
/* Horizontal scroll for tables, code blocks, etc. */
.scrollable-table {
  overflow-x: auto;
  min-width: 0;  /* Still needs this so the parent grid allows shrinking */
}
```

## Related concepts

Responsive layout without media queries is a design principle in this project. See `CLAUDE.md`, section "Width is chosen per content type, not once for the app".

## References

- [CSS Grid: minmax()](https://developer.mozilla.org/en-US/docs/Web/CSS/minmax) — MDN documentation with interactive examples
- [CSS Grid Layout: Common Pitfalls](https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_Grid_Layout#common_issues) — MDN guide to grid overflow and shrinking
- [Grid auto-placement and overflow](https://www.w3.org/TR/css-grid-1/#algo-content-based-sizing) — W3C specification for track sizing
