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


class CardSourceError(RuntimeError):
    """TCGdex respondió algo que no sabemos interpretar.

    Distinta de httpx.HTTPError, que cubre los fallos de transporte. Esta cubre
    los de *contenido*: un 200 con HTML de un proxy caído, un campo que
    desapareció, una categoría nueva que no está en nuestro enum.

    Existe porque sin ella esos casos suben como ValueError o KeyError, esquivan
    el manejo de errores del router y acaban en un 500 — es decir, la aplicación
    se declara culpable de un fallo ajeno. Traducir los errores del proveedor es
    parte del trabajo del adaptador, igual que traducir sus datos.
    """


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
        #
        # Los plazos van separados a propósito, porque distinguen dos situaciones
        # que no merecen la misma paciencia:
        #
        #   connect  — establecer TCP + TLS. Si el host no responde, no va a
        #              responder: esperar más no ayuda. 3s y fuera.
        #   read     — esperar el cuerpo de una conexión ya establecida. Aquí sí
        #              conviene aguantar: el servidor está trabajando.
        #
        # Con un único Timeout(10.0), un host caído hacía esperar diez segundos
        # para decir lo que se sabía a los tres.
        timeout=httpx.Timeout(connect=3.0, read=8.0, write=5.0, pool=2.0),
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


def _parse_list(response: httpx.Response) -> list[dict]:
    """Extrae una lista de objetos del cuerpo, o falla de forma controlada.

    Un 200 no garantiza JSON: un proxy o un CDN delante de TCGdex puede devolver
    una página de error HTML con estado 200. Es el modo de fallo típico de un
    tercero inestable, y sin esta comprobación se manifiesta como un TypeError
    al intentar recorrer la respuesta.
    """
    try:
        payload = response.json()
    except ValueError as exc:  # incluye json.JSONDecodeError
        raise CardSourceError("TCGdex devolvió algo que no es JSON") from exc

    if not isinstance(payload, list):
        raise CardSourceError(f"Se esperaba una lista, llegó {type(payload).__name__}")

    return payload


def _to_summary(payload: dict) -> CardSummary:
    try:
        return CardSummary(
            id=payload["id"],
            name=payload["name"],
            image_url=_image_url(payload.get("image")),
        )
    except (KeyError, TypeError) as exc:
        raise CardSourceError(f"Carta sin los campos mínimos: {exc}") from exc


def _to_card(payload: dict) -> Card:
    """Traduce el JSON de TCGdex a nuestro modelo.

    Aquí es donde el modelo ajeno deja de existir. Nótese `is_ace_spec`: no se
    copia un campo, se deriva una regla.
    """
    legal = payload.get("legal") or {}
    rarity = payload.get("rarity")

    try:
        return Card(
            id=payload["id"],
            name=payload["name"],
            image_url=_image_url(payload.get("image")),
            # ValueError si TCGdex añade una categoría que no tenemos. Es el
            # riesgo de traducir a un enum cerrado, y se prefiere a aceptar
            # cualquier cadena: falla ruidosamente y en un solo sitio.
            category=CardCategory(payload["category"]),
            rarity=rarity,
            regulation_mark=payload.get("regulationMark"),
            legal_standard=bool(legal.get("standard", False)),
            legal_expanded=bool(legal.get("expanded", False)),
            is_ace_spec=rarity == ACE_SPEC_RARITY,
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise CardSourceError(f"No se pudo interpretar la carta: {exc}") from exc


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
        "pagination:itemsPerPage": page_size,
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
    payload = _parse_list(response)

    # TCGdex no devuelve el total de resultados, así que "hay más páginas" se
    # deduce: si vino la página completa, probablemente haya otra.
    #
    # Es una aproximación, y su único fallo es benigno: cuando el total es
    # múltiplo exacto de page_size, la última página ofrece "Siguiente" y la
    # siguiente sale vacía. Preferimos eso a la alternativa —pedir un elemento
    # extra— porque con paginación por número de página `itemsPerPage` también
    # determina el desplazamiento: pedir page_size+1 desplaza la ventana y se
    # salta una carta en cada frontera de página.
    has_more = len(payload) == page_size

    return CardSearchResult(
        cards=[_to_summary(item) for item in payload],
        page=page,
        page_size=page_size,
        has_more=has_more,
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

    try:
        payload = response.json()
    except ValueError as exc:
        raise CardSourceError("TCGdex devolvió algo que no es JSON") from exc

    return _to_card(payload)
