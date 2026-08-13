"""Adaptador de PokeAPI. El único fichero del proyecto que la conoce.

Segundo proveedor externo del proyecto, y se contiene igual que el primero: nadie
fuera de aquí sabe que PokeAPI existe, ni cómo se construye la URL de un sprite.

Es la misma lección que `card_source.py`, y ahora se puede comprobar en lugar de
prometer: cuando TCGdex se cayó el 9 de agosto, cambiar toda la aplicación de
«llamada en vivo» a «consulta local» costó dos imports porque el proveedor estaba
encerrado en un fichero.

Dos diferencias con el adaptador de cartas, ambas por el tamaño del problema:

- No hace falta cliente persistente ni pool: se usa una sola vez, desde el job de
  sincronización, y son dos peticiones en total.
- No hay búsqueda remota. Los 1025 Pokémon caben de sobra en Mongo, y el buscador
  tiene que responder mientras el usuario teclea.
"""

import httpx

from app.models.pokemon import PokemonRef

BASE_URL = "https://pokeapi.co/api/v2"

# Los sprites viven en el repositorio de imágenes de PokeAPI, no en su API. Son
# ficheros estáticos servidos por el CDN de GitHub: ~1 KB cada uno, con fondo
# transparente.
#
# La ilustración oficial existe en la misma ruta bajo other/official-artwork/,
# pero pesa entre 110 y 155 KB. Para un icono de 32 píxeles sería tirar ancho de
# banda a la basura.
SPRITE_URL = (
    "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{}.png"
)

# El límite del Pokédex nacional en el momento de escribir esto. Se pide explícito
# porque PokeAPI pagina de 20 en 20 por defecto.
NATIONAL_DEX_SIZE = 1025


class PokemonSourceError(RuntimeError):
    """PokeAPI respondió algo que no sabemos interpretar.

    Igual que CardSourceError: traducir los errores del proveedor es parte del
    trabajo del adaptador, no solo traducir sus datos.
    """


def sprite_url(dex_id: int) -> str:
    """Compone la URL del sprite a partir del número nacional.

    Vive aquí, y solo aquí, para que un cambio de proveedor o de ruta sea un
    cambio de una línea. Es exactamente lo que hace `_image_url` en el adaptador
    de cartas con las imágenes de TCGdex.
    """
    return SPRITE_URL.format(dex_id)


async def fetch_national_dex() -> list[PokemonRef]:
    """Descarga el Pokédex nacional completo.

    Una sola petición: PokeAPI acepta `limit`, y la lista viene ordenada por
    número, así que el índice del array +1 ES el número nacional. No hace falta
    una llamada por Pokémon —que serían 1025 y el problema N+1 de
    log_mentor/08 en su forma más literal.
    """
    async with httpx.AsyncClient(
        base_url=BASE_URL,
        timeout=httpx.Timeout(connect=3.0, read=20.0, write=5.0, pool=2.0),
        headers={"User-Agent": "pkmtcgbuddy"},
    ) as client:
        response = await client.get(
            "/pokemon", params={"limit": NATIONAL_DEX_SIZE, "offset": 0}
        )
        response.raise_for_status()

        try:
            payload = response.json()
            resultados = payload["results"]
        except (ValueError, KeyError, TypeError) as exc:
            raise PokemonSourceError(f"Respuesta inesperada de PokeAPI: {exc}") from exc

    return [
        PokemonRef(
            dex_id=indice,
            name=entrada["name"],
            sprite_url=sprite_url(indice),
        )
        for indice, entrada in enumerate(resultados, start=1)
    ]
