import { useEffect, useId, useRef, useState } from 'react'
import { useT } from '../i18n/index.jsx'

/**
 * A button that expands into a list of actions.
 *
 * It was born as the "⋮" of a row — replacing the loose "×", because a row
 * with two actions hanging off the margin is noise that gets read on every
 * line even though it's almost never used — and when the folders' "+ New"
 * button arrived it turned out to be the same component with a different
 * trigger. Hence the `trigger` prop and the generic name: it used to be called
 * RowMenu, and keeping that name once it no longer lives only in a row would
 * have been a lie in the name.
 *
 * It's the first dropdown in the project that closes on a click OUTSIDE of
 * it, and that forces listening on `document`: the click that closes it does
 * not happen inside this component, so there's no React onClick that can see
 * it.
 *
 * Two things that listener demands, and that are the lesson of this file:
 *
 *   1. It's registered only while the menu is OPEN. With the menu closed
 *      there's nothing to listen for, and in a list of thirty sessions that
 *      would be thirty permanent listeners.
 *   2. The useEffect RETURNS its cleanup. Without it, every opening leaves
 *      one alive: open and close it ten times and there are ten listeners
 *      firing on every click on the page. It's the classic memory leak of
 *      effects.
 */
export default function Menu({
  actions,
  // No literal default here: the fallback is a translated string, and a
  // default parameter is evaluated once, outside any component render,
  // where useT() has no provider to read from.
  label,
  trigger = '⋮',
  className = '',
  align = 'right',
}) {
  const t = useT()
  // Every current call site passes its own label, so this fallback never
  // fires today — it exists because Menu is shared, and a future caller
  // that omits `label` should still get translated copy, not 'undefined'.
  const resolvedLabel = label ?? t('menu.defaultLabel')
  const [open, setOpen] = useState(false)
  // The root node, so we can ask whether the click landed inside or outside.
  const root = useRef(null)
  // Stable identifier, unique per instance. It's needed because there's one
  // menu per row and aria-controls has to point at ONE. Generating it with
  // Math.random would give a different one on every render.
  const menuId = useId()

  useEffect(() => {
    if (!open) return

    function handleClickOutside(event) {
      // contains() also covers children: clicking a menu option is a click
      // "inside", and closing it there would prevent the action from running.
      if (!root.current?.contains(event.target)) setOpen(false)
    }

    function handleKeyDown(event) {
      if (event.key === 'Escape') setOpen(false)
    }

    // `mousedown`, not `click`: it fires earlier, so the menu closes on press
    // rather than on release. With `click` the menu stays visible while the
    // button is held down and a flicker shows.
    document.addEventListener('mousedown', handleClickOutside)
    document.addEventListener('keydown', handleKeyDown)

    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [open])

  return (
    <div className={`row-menu ${className}`} ref={root}>
      <button
        type="button"
        className="row-menu-trigger"
        /* The three attributes that make this a menu and not a button with a
           div underneath: a screen reader announces that it opens a menu, and
           whether it's open or closed. */
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        aria-label={resolvedLabel}
        title={resolvedLabel}
        onClick={() => setOpen((wasOpen) => !wasOpen)}
      >
        {trigger}
      </button>

      {open && (
        <div
          className={`row-menu-items ${align === 'left' ? 'align-left' : ''}`}
          id={menuId}
          role="menu"
        >
          {actions.map((action) => (
            <button
              key={action.label}
              type="button"
              role="menuitem"
              className={action.danger ? 'danger' : undefined}
              onClick={() => {
                setOpen(false)
                action.onSelect()
              }}
            >
              <span aria-hidden="true">{action.icon}</span>
              {action.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
