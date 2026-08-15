"""Carpetas para organizar los mazos.

Un árbol, y por eso hay una decisión de modelado que merece nombre. MongoDB
documenta cinco formas de guardar un árbol —referencia al padre, referencia a
los hijos, array de antepasados, rutas materializadas y conjuntos anidados— y se
distinguen por qué consulta abaratan:

    referencia al padre    subir es trivial; bajar un subárbol entero necesita
                           $graphLookup o varias vueltas
    array de antepasados   {ancestors: X} da el subárbol de una sola consulta
                           indexada, pero mover una carpeta obliga a reescribir
                           el array de TODOS sus descendientes
    rutas materializadas   igual de rápido con un regex anclado, mismo coste al
                           mover, y además hay que escapar el separador

Aquí se usa **referencia al padre**, la más simple, y el motivo es el tamaño: un
usuario tendrá cinco o diez carpetas. Toda la colección cabe en una consulta y el
árbol se arma en memoria, así que la consulta que la referencia al padre encarece
—bajar por el árbol— aquí no se llega a hacer nunca.

Las otras cuatro existen para colecciones donde traérselo todo es impensable. Con
diez documentos serían maquinaria cara de mantener para acelerar algo que ya es
instantáneo.
"""

from pydantic import BaseModel, Field, field_validator


def _limpia_nombre(valor: str) -> str:
    """Recorta y colapsa espacios. No pasa a minúsculas, al revés que las
    etiquetas: una carpeta es un título que el usuario escribe y quiere ver tal
    cual, no una clave por la que se agrupa."""
    return " ".join(valor.split())


class FolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    parent_id: str | None = None

    @field_validator("name")
    @classmethod
    def normaliza(cls, v: str) -> str:
        return _limpia_nombre(v)


class FolderUpdate(BaseModel):
    """Renombrar o mover.

    Ojo con `parent_id`: aquí `None` **significa algo** —«llévala a la raíz»— y
    no es lo mismo que no mandar el campo. Es justo lo contrario que el `name` de
    un mazo, donde un null solo puede ser un error del cliente y se descarta.

    Los dos casos se distinguen con `exclude_unset`, que separa «no vino» de
    «vino a null». Sin él no habría forma de sacar una carpeta de su padre.
    """

    name: str | None = Field(default=None, min_length=1, max_length=60)
    parent_id: str | None = None

    @field_validator("name")
    @classmethod
    def normaliza(cls, v: str | None) -> str | None:
        return _limpia_nombre(v) if v is not None else None


class FolderOut(BaseModel):
    id: str
    name: str
    parent_id: str | None = None
    # Mazos colgados DIRECTAMENTE de esta carpeta, sin contar los de sus hijas.
    # El total con descendientes lo suma el frontend, que ya tiene el árbol
    # montado: hacerlo aquí obligaría a recorrerlo dos veces.
    deck_count: int = 0
