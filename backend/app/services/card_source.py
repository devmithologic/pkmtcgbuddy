"""Adaptador de TCGdex. El único fichero del proyecto que conoce su API.

Todo lo que sabe el resto del código es que existen funciones que devuelven
`Card` y `CardSearchResult` (ver models/card.py). Nadie más ve una URL de TCGdex,
un nombre de campo suyo, ni su forma de paginar.

Eso es un *adapter*, o *anti-corruption layer*. La ventaja no es teórica: si
TCGdex cierra —como le pasó a pokemontcg.io, ver CLAUDE.md— cambiar de proveedor
es reescribir este fichero, no perseguir `response["legal"]["standard"]` por todo
el repositorio.

Usamos httpx contra la API REST en lugar del SDK oficial. Dos razones: el SDK
esconde el HTTP, que aquí es justamente lo que hay que entender; y sus propios
documentos publican dos modelos de carta incompatibles entre sí, así que la API
es la fuente más fiable de las dos.
"""

import httpx

from app.models.card import (
    Card,
    CardCategory,
    CardSearchResult,
    CardSummary,
    DeckFormat,
)

BASE_URL = "https://api.tcgdex.net/v2/en"

# TCGdex marca las ACE SPEC como una rareza. Esta constante es la única aparición
# de la cadena en todo el proyecto; el resto del código pregunta por is_ace_spec.
ACE_SPEC_RARITY = "ACE SPEC Rare"

# El cliente se abre en el lifespan de la app, igual que el de Mongo, y por el
# mismo motivo: reutilizar conexiones TCP en vez de negociar TLS en cada búsqueda.
_client: httpx.AsyncClient | None = None


async def connect_card_source() -> None:
    global _client
    _client = httpx.AsyncClient(
        base_url=BASE_URL,
        # Sin timeout, una TCGdex lenta deja peticiones nuestras colgadas
        # indefinidamente y acaba agotando el pool de conexiones. Es la forma más
        # común de que el fallo de un tercero se convierta en tu caída.
        timeout=httpx.Timeout(10.0),
        headers={"User-Agent": "pkmtcgbuddy"},
    )


async def close_card_source() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def _require_client() -> httpx.AsyncClient:
    if _client is None:
        raise RuntimeError("El cliente de TCGdex no está abierto: ¿corrió el lifespan?")
    return _client


def _image_url(base: str | None, quality: str = "low") -> str | None:
    """TCGdex devuelve la imagen sin extensión: hay que componer la URL final.

    'https://assets.tcgdex.net/en/sv/sv03/125' -> '.../125/low.webp'

    Detalle del proveedor que no debe salir de este fichero.
    """
    return f"{base}/{quality}.webp" if base else None


def _to_summary(payload: dict) -> CardSummary:
    return CardSummary(
        id=payload["id"],
        name=payload["name"],
        image_url=_image_url(payload.get("image")),
    )


def _to_card(payload: dict) -> Card:
    """Traduce el JSON de TCGdex a nuestro modelo.

    Aquí es donde el modelo ajeno deja de existir. Nótese `is_ace_spec`: no se
    copia un campo, se deriva una regla.
    """
    legal = payload.get("legal") or {}
    rarity = payload.get("rarity")

    return Card(
        id=payload["id"],
        name=payload["name"],
        image_url=_image_url(payload.get("image")),
        category=CardCategory(payload["category"]),
        rarity=rarity,
        regulation_mark=payload.get("regulationMark"),
        legal_standard=bool(legal.get("standard", False)),
        legal_expanded=bool(legal.get("expanded", False)),
        is_ace_spec=rarity == ACE_SPEC_RARITY,
    )


async def search_cards(
    name: str | None = None,
    deck_format: DeckFormat | None = None,
    category: CardCategory | None = None,
    ace_spec_only: bool = False,
    page: int = 1,
    page_size: int = 24,
) -> CardSearchResult:
    """Busca cartas. Los filtros se combinan con AND.

    La búsqueda por nombre es por SUBCADENA y sin distinguir mayúsculas, no por
    prefijo: "rod" devuelve "Aerodactyl" (ae-ROD-actyl). No es un fallo, es cómo
    filtra TCGdex, y conviene que la interfaz lo advierta.
    """
    params: dict[str, str | int] = {
        "pagination:page": page,
        # Pedimos uno de más para saber si existe página siguiente sin necesitar
        # un total que la API no da. Truco habitual en paginación por cursor.
        "pagination:itemsPerPage": page_size + 1,
        "sort:field": "name",
        "sort:order": "ASC",
    }

    if name:
        params["name"] = name
    if category:
        params["category"] = category.value
    if ace_spec_only:
        params["rarity"] = ACE_SPEC_RARITY
    if deck_format:
        # 'legal.standard' / 'legal.expanded': el punto es sintaxis de TCGdex para
        # filtrar por un campo anidado.
        params[f"legal.{deck_format.value}"] = "true"

    response = await _require_client().get("/cards", params=params)
    response.raise_for_status()
    payload = response.json()

    has_more = len(payload) > page_size
    cards = [_to_summary(item) for item in payload[:page_size]]

    return CardSearchResult(
        cards=cards, page=page, page_size=page_size, has_more=has_more
    )


async def get_card(card_id: str) -> Card | None:
    """Detalle de una carta. Devuelve None si no existe.

    Hace falta un endpoint aparte porque el listado de TCGdex solo entrega
    id, nombre e imagen: filtra por campos que no devuelve.

    Consecuencia a tener presente: pintar la rareza de 24 resultados exigiría 24
    llamadas extra. Eso es el problema **N+1** — una consulta para la lista más
    una por elemento. Por eso la búsqueda muestra solo nombre e imagen, y el
    detalle se pide cuando el usuario elige una carta concreta.
    """
    response = await _require_client().get(f"/cards/{card_id}")

    if response.status_code == 404:
        return None
    response.raise_for_status()

    return _to_card(response.json())
