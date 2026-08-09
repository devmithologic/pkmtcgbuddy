# Cumulative Layout Shift and Lazy Images

> **Stack:** CSS · **Introduced in:** card search — the results grid collapsed · **Date:** 2026-08-08

## Definition

**Cumulative Layout Shift (CLS)** measures how much visible content moves position while a page
loads. It happens whenever an element's size is unknown until its content arrives, so the browser
lays out the page twice: once without it, once with.

## Why it exists

An `<img>` with no declared dimensions occupies **zero height** until the image loads. The browser
cannot know how tall it will be, so it reserves nothing, lays out everything below at the top, and
then reflows once the bytes arrive.

`loading="lazy"` makes this worse, not better. A lazy image outside the viewport is never requested,
so it stays at zero height indefinitely — and its zero height is what keeps it out of the viewport.
The two conditions sustain each other.

The user-facing symptom is the familiar one: a page settles, you reach for a link, and it jumps out
from under your finger as an image above it finally loads. CLS is one of Google's Core Web Vitals for
exactly this reason.

## How it works

Tell the browser the shape before the content exists. Modern CSS does it in one line:

```css
img {
  width: 100%;
  aspect-ratio: 245 / 342;   /* reserves height from width */
}
```

The browser computes the height from the width and the ratio, reserves the box during first layout,
and the image drops into a space that was already the right size. No reflow, no shift.

Two older approaches still appear and are worth recognising:

- **`width` and `height` HTML attributes.** Since 2019, browsers derive an implicit `aspect-ratio`
  from them, so `<img width="245" height="342">` works even when CSS overrides the actual size.
- **The padding-top hack** — a wrapper with `padding-top: 139.6%` — was the only option before
  `aspect-ratio` and is now unnecessary.

Reserving space is not only for images. Skeleton placeholders, ad slots, and embedded iframes cause
the same shift for the same reason.

## In this project

The bug was visible the first time the search grid rendered: rows had wildly different heights, some
cards showed only a name where a picture should be, and the grid re-flowed as images arrived.

The mistake was setting `loading="lazy"` without reserving space:

```jsx
// frontend/src/components/CardSearch.jsx
<img src={card.image_url} alt={card.name} loading="lazy" />
```

```css
/* frontend/src/App.css — before */
.card-grid img {
  width: 100%;
}
```

Width was defined; height was not. Every not-yet-loaded card measured zero, so grid rows sized
themselves to whatever had already loaded, and the placeholder cells for cards genuinely without
images — which *did* have a reserved size — stood out as the only tall boxes on the page. The
inconsistency is what gave the cause away: cells with a size and cells without, side by side.

```css
/* frontend/src/App.css — after */
.card-grid img {
  width: 100%;
  aspect-ratio: 245 / 342;          /* real proportions of a Pokémon card */
  background: rgb(128 128 128 / 0.1);
  object-fit: cover;
}
```

`245 / 342` is the actual pixel ratio of a TCG card image, so the reserved box matches what arrives.
The faint background makes the reserved space visible while loading, which turns a blank gap into an
obvious placeholder. `object-fit: cover` guarantees that an image with unexpected proportions fills
the box rather than distorting.

The `.no-image` placeholder already used the same ratio; making the two agree is what made rows line
up.

## Gotchas

- **`aspect-ratio` is ignored if both width and height are set.** It computes the missing dimension;
  give it only one.
- **`loading="lazy"` without reserved space can prevent loading entirely.** Zero-height images never
  intersect the viewport, so the browser never decides they are needed.
- **A wrong ratio still shifts, just less.** Measure the real asset instead of guessing.
- **`object-fit` needs a sized box to do anything.** It controls how content fills a box; without
  dimensions there is no box.
- **CLS is measured on user-visible movement, not load time.** A page can score badly while being
  fast, and the fix is layout, not performance.

## Related concepts

Core Web Vitals (LCP, INP, CLS); skeleton screens; `content-visibility` for deferring off-screen
rendering; responsive images with `srcset`.

## References

- [Cumulative Layout Shift (CLS) — web.dev](https://web.dev/articles/cls) — the metric, what causes it, and how it is scored
- [aspect-ratio — MDN](https://developer.mozilla.org/en-US/docs/Web/CSS/aspect-ratio) — syntax and interaction with width/height
- [Lazy loading — MDN](https://developer.mozilla.org/en-US/docs/Web/Performance/Guides/Lazy_loading) — when `loading="lazy"` helps and what it requires
