"""Acceso a la colección `cards` de MongoDB.

Este módulo es el gemelo local de services/card_source.py. Uno lee de TCGdex,
el otro de nuestra base. Ambos devuelven los mismos modelos —Card, CardSummary,
CardSearchResult— así que el router puede cambiar de uno a otro sin enterarse.

Esa simetría no es casual: es lo que hace posible sustituir "llamada en vivo" por
"consulta local" cambiando dos líneas del router. Cuando el adaptador se escribió,
esa ventaja era una promesa; aquí es donde se cobra.

El patrón se llama *repository*: una capa que encapsula el acceso a datos y expone
operaciones del dominio ("busca cartas legales en Standard") en lugar de detalles
de almacenamiento (filtros, índices, cursores).
"""

from datetime import datetime, timezone

from pymongo import ASCENDING

from app.db.mongo import get_database
from app.models.card import (
    Card,
    CardCategory,
    CardSearchResult,
    CardSummary,
    DeckFormat,
)

COLLECTION = "cards"


def _collection():
    return get_database()[COLLECTION]


async def ensure_indexes() -> None:
    """Crea los índices que necesitan las búsquedas.

    Sin índice, cada consulta recorre la colección entera (*collection scan*).
    Con ~20.000 cartas eso son milisegundos y no se nota; el hábito importa
    igualmente, porque el día que no se note ya será tarde.

    create_index es idempotente: si el índice existe, no hace nada. Por eso se
    puede llamar en cada arranque sin comprobar antes.
    """
    collection = _collection()
    # Compuesto, y en este orden: soporta tanto ordenar por nombre como el
    # desempate por _id que hace determinista la paginación.
    await collection.create_index([("name_lower", ASCENDING), ("_id", ASCENDING)])
    await collection.create_index([("category", ASCENDING)])
    await collection.create_index([("legal_standard", ASCENDING)])
    await collection.create_index([("legal_expanded", ASCENDING)])
    await collection.create_index([("is_ace_spec", ASCENDING)])


def card_to_document(card: Card) -> dict:
    """Convierte una Card en documento almacenable.

    Usa el id de TCGdex como _id en lugar de dejar que Mongo genere un ObjectId.
    Es una *clave natural*: ya identifica la carta de forma única y estable, así
    que reutilizarla hace que volver a sincronizar sea un upsert trivial en vez
    de una búsqueda por otro campo.
    """
    return {
        "_id": card.id,
        "name": card.name,
        # Campo derivado, guardado a propósito: buscar sin distinguir mayúsculas
        # con una expresión regular sensible a ellas obligaría a Mongo a
        # transformar cada documento en tiempo de consulta, y ningún índice
        # podría ayudar. Precalcular es la versión barata.
        "name_lower": card.name.lower(),
        "image_url": card.image_url,
        "category": card.category.value,
        "rarity": card.rarity,
        "regulation_mark": card.regulation_mark,
        "legal_standard": card.legal_standard,
        "legal_expanded": card.legal_expanded,
        "is_ace_spec": card.is_ace_spec,
        "is_basic_energy": card.is_basic_energy,
        "synced_at": datetime.now(timezone.utc),
    }


def card_from_document(document: dict) -> Card:
    return Card(
        id=document["_id"],
        name=document["name"],
        image_url=document.get("image_url"),
        category=CardCategory(document["category"]),
        rarity=document.get("rarity"),
        regulation_mark=document.get("regulation_mark"),
        legal_standard=document["legal_standard"],
        legal_expanded=document["legal_expanded"],
        is_ace_spec=document["is_ace_spec"],
        # .get con defecto: los documentos escritos antes de que existiera el
        # campo no lo tienen. Una resincronización los completa.
        is_basic_energy=document.get("is_basic_energy", False),
    )


def _build_filter(
    name: str | None,
    deck_format: DeckFormat | None,
    category: CardCategory | None,
    ace_spec_only: bool,
) -> dict:
    """Traduce los filtros del dominio a una consulta de MongoDB."""
    query: dict = {}

    if name:
        # $regex sin anclar reproduce el comportamiento de TCGdex: subcadena, no
        # prefijo. "rod" encuentra "Aerodactyl".
        #
        # re.escape es obligatorio: sin él, un usuario que teclee "(" o "*"
        # provoca una expresión inválida, y patrones como "(a+)+" son un vector
        # de denegación de servicio por backtracking catastrófico (ReDoS).
        import re

        query["name_lower"] = {"$regex": re.escape(name.lower())}

    if category:
        query["category"] = category.value

    if ace_spec_only:
        query["is_ace_spec"] = True

    if deck_format:
        query[f"legal_{deck_format.value}"] = True

    return query


async def search_cards(
    name: str | None = None,
    deck_format: DeckFormat | None = None,
    category: CardCategory | None = None,
    ace_spec_only: bool = False,
    page: int = 1,
    page_size: int = 24,
) -> CardSearchResult:
    """Busca en la colección local. Misma firma que card_source.search_cards."""
    query = _build_filter(name, deck_format, category, ace_spec_only)

    # skip/limit sobre nuestra propia base sí permite el truco de pedir uno de
    # más, porque aquí el desplazamiento es explícito y no depende del límite.
    # Es justo lo que no se podía hacer contra la paginación por número de
    # página de TCGdex.
    skip = (page - 1) * page_size

    cursor = (
        _collection()
        .find(query, {"name": 1, "image_url": 1})
        # Se ordena por (name_lower, _id), no solo por name_lower.
        #
        # El nombre NO es único: hay decenas de cartas llamadas "Pikachu", y
        # entre las ACE SPEC hay cuatro nombres repetidos. Con una clave de orden
        # que admite empates, MongoDB no garantiza en qué orden devuelve los
        # empatados, y puede resolverlos distinto en dos ejecuciones de la misma
        # consulta —depende del plan que elija, que a su vez depende del límite.
        #
        # Sobre una sola consulta da igual. Al paginar con skip/limit es un fallo:
        # cada página es una consulta independiente, así que un empate que caiga
        # justo en la frontera puede hacer que una carta salga en las dos páginas
        # o en ninguna. Añadir _id —único por definición— hace el orden TOTAL y
        # por tanto determinista.
        .sort([("name_lower", ASCENDING), ("_id", ASCENDING)])
        .skip(skip)
        .limit(page_size + 1)
    )

    documents = [doc async for doc in cursor]
    has_more = len(documents) > page_size

    return CardSearchResult(
        cards=[
            CardSummary(
                id=doc["_id"], name=doc["name"], image_url=doc.get("image_url")
            )
            for doc in documents[:page_size]
        ],
        page=page,
        page_size=page_size,
        has_more=has_more,
    )


async def get_card(card_id: str) -> Card | None:
    """Detalle de una carta. Aquí no hay problema N+1 que evitar: la búsqueda
    podría devolver el documento completo sin coste extra. Se mantiene la
    división en dos endpoints por compatibilidad con lo que ya usa el frontend."""
    document = await _collection().find_one({"_id": card_id})
    return card_from_document(document) if document else None


async def get_cards_by_ids(card_ids: list[str]) -> dict[str, Card]:
    """Resuelve varias cartas de una vez. Devuelve {card_id: Card}.

    Existe para validar un mazo. Un mazo son hasta 60 entradas, y la regla de las
    4 copias necesita el nombre de cada una — pedirlas de una en una serían 60
    consultas: el problema N+1 de log_mentor/08, esta vez contra nuestra propia
    base en lugar de contra una API.

    `$in` las trae todas en una sola consulta, y el índice sobre _id la resuelve
    directamente. Devolver un dict en vez de una lista es deliberado: quien valida
    necesita buscar por id, y una lista le obligaría a recorrerla por cada carta.

    Los ids que no existan simplemente no aparecen en el resultado; detectarlo es
    trabajo de deck_rules, que emite UNKNOWN_CARD.
    """
    if not card_ids:
        return {}

    # set() elimina duplicados: una lista puede repetir el mismo id si el cliente
    # manda dos entradas de la misma carta.
    cursor = _collection().find({"_id": {"$in": list(set(card_ids))}})
    return {doc["_id"]: card_from_document(doc) async for doc in cursor}


async def count_cards() -> int:
    """Cuántas cartas hay sincronizadas. Sirve para distinguir «no hay
    resultados» de «nunca se ha sincronizado», que son problemas distintos."""
    return await _collection().count_documents({})
