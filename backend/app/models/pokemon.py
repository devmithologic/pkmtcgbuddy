"""Referencia a un Pokémon.

Sirve para identificar visualmente un mazo —el tuyo o el del rival— con uno o dos
iconos, que es como se leen los emparejamientos de un torneo de un vistazo.

No es una carta. Una carta es una impresión concreta con su set y su rareza; esto
es la criatura, y su número nacional es estable para siempre.
"""

from pydantic import BaseModel


class PokemonRef(BaseModel):
    """Un Pokémon, tal como se guarda dentro de un mazo o de una ronda.

    Guarda `dex_id` **y** `name` aunque el nombre sea derivable del número. Es
    duplicación deliberada y acotada, y merece justificarse porque en este
    proyecto se ha evitado sistemáticamente:

    - El dato es inmutable. Dragapult será el 887 siempre; no hay una
      resincronización que pueda dejar el nombre obsoleto.
    - Evita resolver 1025 nombres al leer una lista de sesiones. Sin ello, cada
      ronda necesitaría una búsqueda para poder escribir su etiqueta.

    Cuando el dato duplicado *puede* cambiar —el nombre de una carta, la
    legalidad, el récord de una sesión— no se guarda. Aquí no puede.
    """

    dex_id: int
    name: str
    sprite_url: str
