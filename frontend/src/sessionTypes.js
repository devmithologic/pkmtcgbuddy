/**
 * Session types, in a module of their own rather than inside a component.
 *
 * The reason is concrete, not stylistic: Vite hot-reloads a file only if it
 * exports components exclusively. Exporting constants too forces a full page
 * reload on every change and the state is lost.
 *
 * These values must match SessionType in backend/app/models/session.py. They are
 * wire values — never translate them. The human-readable label lives in the
 * catalogue under `sessionType.<value>`, because it changes with the locale and
 * a module constant cannot.
 */
export const SESSION_TYPES = ['league', 'cup', 'challenge', 'online', 'testing']
