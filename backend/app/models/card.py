"""Nuestro modelo de carta.

Esto NO es la forma que devuelve TCGdex. Es la forma que necesita esta aplicación,
y la diferencia es deliberada: el resto del código depende de estos modelos, nunca
del JSON del proveedor.

El patrón se llama *anti-corruption layer* — una capa que impide que el modelo de
un sistema externo se filtre dentro del tuyo. Ver services/card_source.py, que es
donde ocurre la traducción.

Ejemplo concreto de por qué importa: TCGdex codifica que una carta es ACE SPEC
dentro del campo `rarity`, con el literal "ACE SPEC Rare". Nuestro dominio no
quiere una cadena mágica repartida por el código; quiere un booleano `is_ace_spec`.
Si mañana TCGdex renombra esa rareza, cambia un fichero.
"""

from enum import Enum

from pydantic import BaseModel


class CardCategory(str, Enum):
    """Las tres categorías de carta. Valores tomados de GET /v2/en/categories."""

    POKEMON = "Pokemon"
    TRAINER = "Trainer"
    ENERGY = "Energy"


class DeckFormat(str, Enum):
    """Formatos de torneo que soporta la aplicación.

    Vive aquí, y no en el módulo de mazos, porque la legalidad es una propiedad de
    la carta: el formato solo tiene sentido como filtro sobre cartas.
    """

    STANDARD = "standard"
    EXPANDED = "expanded"


class CardSummary(BaseModel):
    """Lo que devuelve una búsqueda.

    Es lo que el listado de TCGdex entrega: id, nombre e imagen. Deliberadamente
    pobre — ver la nota sobre N+1 en services/card_source.py.
    """

    id: str
    name: str
    image_url: str | None = None


class Card(CardSummary):
    """Una carta con el detalle que necesita el constructor de mazos."""

    category: CardCategory
    rarity: str | None = None
    regulation_mark: str | None = None
    legal_standard: bool
    legal_expanded: bool

    # Derivado, no copiado: TCGdex lo expresa como rarity == "ACE SPEC Rare".
    is_ace_spec: bool

    # Huella de QUÉ carta es, compartida por todas sus reimpresiones. La calcula
    # el adaptador a partir del nombre y el texto; no del set ni la rareza.
    #
    # Sirve para la regla de reimpresión: si Boss's Orders se reimprime en un set
    # legal, las impresiones antiguas del mismo texto también se pueden jugar, y
    # TCGdex no lo modela. Ver services/card_sync.py.
    identity: str = ""

    # También derivado, y con una traducción de vocabulario por medio: TCGdex
    # llama "Normal" a lo que el reglamento llama energía *básica*. Guardamos el
    # término del dominio, no el del proveedor.
    #
    # Importa porque la regla de "máximo 4 copias por nombre" exime justamente a
    # la energía básica: un mazo puede llevar veinte Lightning Energy.
    is_basic_energy: bool = False

    def is_legal_in(self, deck_format: DeckFormat) -> bool:
        """Regla de dominio, no dato del proveedor. La usará la validación de
        mazos en el siguiente slice."""
        return {
            DeckFormat.STANDARD: self.legal_standard,
            DeckFormat.EXPANDED: self.legal_expanded,
        }[deck_format]


class CardSearchResult(BaseModel):
    """Una página de resultados.

    Devolvemos la página envuelta en un objeto en lugar de un array pelado porque
    el cliente necesita saber en qué página está para poder pedir la siguiente. Un
    array no tiene sitio donde colgar esa información.

    No incluye el total de resultados: TCGdex no lo da sin descargar la colección
    entera, y mentir con un número inventado sería peor que omitirlo.
    """

    cards: list[CardSummary]
    page: int
    page_size: int
    has_more: bool
