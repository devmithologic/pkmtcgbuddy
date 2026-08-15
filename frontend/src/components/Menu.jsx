import { useEffect, useId, useRef, useState } from 'react'

/**
 * Un botón que despliega una lista de acciones.
 *
 * Nació como el «⋮» de una fila —sustituyendo a la «×» suelta, porque una fila
 * con dos acciones colgadas del margen es ruido que se lee en cada renglón
 * aunque casi nunca se use— y al llegar el botón «+ Nuevo» de las carpetas
 * resultó ser el mismo componente con otro disparador. De ahí el prop `trigger`
 * y el nombre genérico: se llamaba RowMenu, y seguir llamándolo así cuando ya no
 * vive solo en una fila habría sido mentir en el nombre.
 *
 * Es el primer desplegable del proyecto que se cierra al pulsar FUERA de él, y
 * eso obliga a escuchar en `document`: el clic que lo cierra no ocurre dentro de
 * este componente, así que no hay ningún onClick de React que lo pueda ver.
 *
 * Dos cosas que ese listener exige y que son la lección de este fichero:
 *
 *   1. Se registra solo cuando el menú está ABIERTO. Con el menú cerrado no hay
 *      nada que escuchar, y en una lista de treinta sesiones serían treinta
 *      listeners permanentes.
 *   2. El useEffect DEVUELVE su limpieza. Sin ella, cada apertura deja uno vivo:
 *      abres y cierras diez veces y hay diez listeners ejecutándose a cada clic
 *      de la página. Es la fuga de memoria clásica de los efectos.
 */
export default function Menu({
  actions,
  label = 'Acciones',
  trigger = '⋮',
  className = '',
  align = 'right',
}) {
  const [open, setOpen] = useState(false)
  // El nodo raíz, para poder preguntar si el clic cayó dentro o fuera.
  const root = useRef(null)
  // Identificador estable y único por instancia. Hace falta porque hay un menú
  // por fila y aria-controls tiene que apuntar a UNO. Generarlo con Math.random
  // daría uno distinto en cada render.
  const menuId = useId()

  useEffect(() => {
    if (!open) return

    function alPulsarFuera(event) {
      // contains() cubre también los hijos: pulsar una opción del menú es un
      // clic «dentro», y cerrarlo ahí impediría que la acción se ejecutara.
      if (!root.current?.contains(event.target)) setOpen(false)
    }

    function alPulsarTecla(event) {
      if (event.key === 'Escape') setOpen(false)
    }

    // `mousedown` y no `click`: se dispara antes, así que el menú se cierra al
    // apretar en lugar de al soltar. Con `click` el menú sigue visible mientras
    // el botón está pulsado y se ve un parpadeo.
    document.addEventListener('mousedown', alPulsarFuera)
    document.addEventListener('keydown', alPulsarTecla)

    return () => {
      document.removeEventListener('mousedown', alPulsarFuera)
      document.removeEventListener('keydown', alPulsarTecla)
    }
  }, [open])

  return (
    <div className={`row-menu ${className}`} ref={root}>
      <button
        type="button"
        className="row-menu-trigger"
        /* Los tres atributos que hacen que esto sea un menú y no un botón con
           un div debajo: un lector de pantalla anuncia que abre un menú, y si
           está abierto o cerrado. */
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        aria-label={label}
        title={label}
        onClick={() => setOpen((estaba) => !estaba)}
      >
        {trigger}
      </button>

      {open && (
        <div
          className={`row-menu-items ${align === 'left' ? 'align-left' : ''}`}
          id={menuId}
          role="menu"
        >
          {actions.map((accion) => (
            <button
              key={accion.label}
              type="button"
              role="menuitem"
              className={accion.danger ? 'danger' : undefined}
              onClick={() => {
                setOpen(false)
                accion.onSelect()
              }}
            >
              <span aria-hidden="true">{accion.icon}</span>
              {accion.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
