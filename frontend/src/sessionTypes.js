/**
 * Session types, in a separate module rather than inside a component.
 *
 * The reason is concrete, not stylistic: Vite hot-reloads a file only if it
 * exports components exclusively. Exporting constants too means every change
 * forces a full page reload and the state is lost.
 *
 * The values have to match SessionType in backend/app/models/session.py.
 */

export const SESSION_TYPES = [
  { value: 'league', label: 'League' },
  { value: 'cup', label: 'Cup' },
  { value: 'challenge', label: 'Challenge' },
  { value: 'online', label: 'Online' },
  { value: 'testing', label: 'Testing' },
]

export const TYPE_LABEL = Object.fromEntries(
  SESSION_TYPES.map((t) => [t.value, t.label]),
)
