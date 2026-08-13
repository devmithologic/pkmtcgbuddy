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

# Todas las entradas de PokeAPI, no solo el Pokédex nacional.
#
# El nacional son 1025, pero por encima viven 326 formas más: las 97 MEGA
# EVOLUCIONES, las Gigantamax, las variantes regionales y las formas alternas
# (deoxys-attack, rotom-heat). Las megas hacen falta —el TCG tiene ahora mismo
# sets de Mega Evolution— y el resto no estorba: son documentos de tres campos.
#
# Se pide un límite holgado en vez del count exacto para no encadenar dos
# peticiones. PokeAPI devuelve lo que haya.
FETCH_LIMIT = 3000


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


def _id_from_url(url: str) -> int:
    """Extrae el id de la URL del recurso: .../pokemon/10033/ -> 10033.

    Hace falta porque el id NO se puede deducir de la posición en la lista.
    La primera versión de este fichero usaba enumerate(), y funcionaba de
    casualidad: del 1 al 1025 el índice coincide con el número nacional. Las
    megas empiezan en 10033, así que en cuanto se pidió la lista completa el
    supuesto se rompió y todas habrían quedado con el id equivocado.

    Es el tipo de suposición que solo se ve cuando cambian los datos, no cuando
    cambia el código.
    """
    return int(url.rstrip("/").rsplit("/", 1)[-1])


async def fetch_all() -> list[PokemonRef]:
    """Descarga todas las entradas: nacional, megas, Gigantamax y formas.

    Una sola petición. Pedir el detalle de cada una serían 1351 llamadas: el
    problema N+1 de log_mentor/08 en su forma más literal.
    """
    async with httpx.AsyncClient(
        base_url=BASE_URL,
        timeout=httpx.Timeout(connect=3.0, read=20.0, write=5.0, pool=2.0),
        headers={"User-Agent": "pkmtcgbuddy"},
    ) as client:
        response = await client.get("/pokemon", params={"limit": FETCH_LIMIT, "offset": 0})
        response.raise_for_status()

        try:
            payload = response.json()
            resultados = payload["results"]
        except (ValueError, KeyError, TypeError) as exc:
            raise PokemonSourceError(f"Respuesta inesperada de PokeAPI: {exc}") from exc

    referencias = []
    for entrada in resultados:
        try:
            ident = _id_from_url(entrada["url"])
        except (KeyError, ValueError):
            # Una entrada con URL rara no debe tumbar la sincronización entera.
            continue
        referencias.append(
            PokemonRef(dex_id=ident, name=entrada["name"], sprite_url=sprite_url(ident))
        )
    return referencias
