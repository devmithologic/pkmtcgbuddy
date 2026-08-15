"""Referencia a un Pokémon.

Sirve para identificar visualmente un mazo —el tuyo o el del rival— con uno o dos
iconos, que es como se leen los emparejamientos de un torneo de un vistazo.

No es una carta. Una carta es una impresión concreta con su set y su rareza; esto
es la criatura, y su número nacional es estable para siempre.
"""

from pydantic import BaseModel, computed_field

from app.services.pokemon_source import art_url, icon_url


class PokemonRef(BaseModel):
    """Lo que se guarda y lo que se acepta: el número y el nombre. Nada más.

    Guarda `dex_id` **y** `name` aunque el nombre sea derivable del número. Es
    duplicación deliberada y acotada:

    - El dato es inmutable. Dragapult será el 887 siempre; no hay una
      resincronización que pueda dejar el nombre obsoleto.
    - Evita resolver 1351 nombres al leer una lista de sesiones. Sin ello, cada
      ronda necesitaría una búsqueda para poder escribir su etiqueta.

    Aquí vivía también `sprite_url`, con la misma justificación, y **estaba mal**.
    La URL no es inmutable: es un detalle del proveedor, exactamente lo que
    `pokemon_source.py` existe para encerrar. Al guardarla, se copió dentro de
    cada mazo y de cada ronda, así que el proveedor acabó filtrado a la base de
    datos y la promesa de «cambiar de proveedor es una línea» dejó de ser cierta:
    cambiar la constante no habría tocado ni una de las rondas ya registradas.

    Es la misma regla que ya está escrita para las etiquetas en CLAUDE.md, vista
    desde el otro lado: guarda lo que los datos no pueden expresar, deriva lo que
    sí. Los documentos viejos conservan su clave `sprite_url`; Pydantic ignora
    los campos que no declara, así que sobra sin estorbar y no hizo falta migrar
    nada.
    """

    dex_id: int
    name: str


class PokemonRefOut(PokemonRef):
    """Lo que sale por la API: lo guardado, más las dos URLs calculadas al leer.

    Van en una subclase y no en `PokemonRef` por una razón muy concreta:
    `model_dump()` **incluye** los campos calculados. Las rondas se escriben con
    `**match.model_dump(mode="json")` en `session_repository`, así que unos
    computed_field en el modelo de entrada volverían a meter las URLs en Mongo
    por la puerta de atrás — justo el problema que estamos quitando.

    Separar entrada y salida es el patrón DTO que el proyecto ya usa en
    Create/Out por todas partes. Aquí, además, hace de barrera física.

    Dos URLs y no una porque los dos usos son incompatibles: el render de HOME
    pesa 124 KB y a 20 resultados de buscador son 2.5 MB, mientras que el sprite
    de 1.2 KB a 56 píxeles se ve como una mancha.
    """

    @computed_field
    @property
    def icon_url(self) -> str:
        """Sprite de 96×96. Listas densas: buscador, rondas de una sesión."""
        return icon_url(self.dex_id)

    @computed_field
    @property
    def art_url(self) -> str:
        """Render de HOME, 512×512. Cabecera de mazo y listado de mazos."""
        return art_url(self.dex_id)
