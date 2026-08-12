/**
 * Tipos de sesión, en un módulo aparte y no dentro de un componente.
 *
 * El motivo es concreto, no estilístico: Vite recarga en caliente un fichero
 * solo si exporta únicamente componentes. Al exportar también constantes, cada
 * cambio fuerza una recarga completa de la página y se pierde el estado.
 *
 * Los valores tienen que coincidir con SessionType en backend/app/models/session.py.
 */

export const SESSION_TYPES = [
  { value: 'league', label: 'Liga' },
  { value: 'cup', label: 'Cup' },
  { value: 'challenge', label: 'Challenge' },
  { value: 'online', label: 'Online' },
  { value: 'testing', label: 'Testing' },
]

export const TYPE_LABEL = Object.fromEntries(
  SESSION_TYPES.map((t) => [t.value, t.label]),
)
