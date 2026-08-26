"""Acceso a la colección `sets`.

Unos 218 documentos de cuatro campos: id de TCGdex, nombre, **abreviatura
oficial** y **fecha de publicación**.

La abreviatura existe por una sola razón, y conviene decirla: el formato de
texto con el que se intercambian listas de mazo identifica cada carta por
`<abreviatura> <número>` —`MEG 77`— y la abreviatura no está en ninguna parte
del id de TCGdex, que para esa misma carta es `me01-077`. Sin ella no hay
importación ni exportación posibles.

La fecha existe por otra: es lo único que sabe cuál de las 26 impresiones de
Metal Energy es la vigente. Solo 188 sets tienen abreviatura, pero los 218
tienen fecha y sus cartas salen todas en el buscador; por eso se guardan todos y
la abreviatura puede ser None.
"""

from pymongo import ASCENDING, UpdateOne
from pymongo.errors import OperationFailure

from app.db.mongo import get_database

COLLECTION = "sets"


def _collection():
    return get_database()[COLLECTION]


async def ensure_indexes() -> None:
    # Único pero PARCIAL. Para Mongo, varios documentos sin abreviatura no son
    # "varios sin valor": son varios con el mismo valor null, y un índice único
    # normal rechazaría el segundo. Con partialFilterExpression el índice solo
    # cubre los documentos cuya abreviatura es una cadena, así que los 30 sets
    # sin código entran sin pelearse entre ellos y los 188 con código siguen sin
    # poder duplicarse.
    try:
        await _collection().create_index(
            [("abbreviation", ASCENDING)],
            unique=True,
            partialFilterExpression={"abbreviation": {"$type": "string"}},
        )
    except OperationFailure:
        # El índice ya existe con las opciones viejas —único a secas—, y Mongo
        # no reescribe opciones: hay que tirarlo y volver a crearlo. Pasa una
        # vez, en el primer arranque después de este cambio.
        await _collection().drop_index("abbreviation_1")
        await _collection().create_index(
            [("abbreviation", ASCENDING)],
            unique=True,
            partialFilterExpression={"abbreviation": {"$type": "string"}},
        )


async def abbreviation_map() -> dict[str, str]:
    """{ABREVIATURA: set_id}, la colección entera en un diccionario.

    Se trae todo de golpe y se resuelve en memoria por lo mismo que las
    carpetas: son 190 documentos diminutos, y una lista de mazo tiene veintitrés
    líneas que consultar. Una consulta por línea sería el problema N+1 sobre una
    tabla que cabe en un suspiro.

    Filtra por $type string: los 30 sets sin abreviatura meterían None como
    clave, y entonces una línea de lista cuyo código no se reconociera resolvería
    contra el set None en vez de quedarse sin resolver.
    """
    cursor = _collection().find({"abbreviation": {"$type": "string"}}, {"abbreviation": 1})
    return {doc["abbreviation"]: doc["_id"] async for doc in cursor}


async def id_map() -> dict[str, str]:
    """El diccionario inverso, {set_id: ABREVIATURA}, para exportar.

    Mismo filtro: un set sin abreviatura simplemente no está, y el exportador ya
    sabe qué hacer cuando no encuentra el código de una carta.
    """
    cursor = _collection().find({"abbreviation": {"$type": "string"}}, {"abbreviation": 1})
    return {doc["_id"]: doc["abbreviation"] async for doc in cursor}


async def release_dates() -> dict[str, str]:
    """{set_id: "YYYY-MM-DD"}, para poder ordenar impresiones por antigüedad.

    Se trae entera por lo mismo que los otros dos mapas: son 218 documentos de
    cuatro campos, y quien la usa —el rellenado de cartas— los necesita todos.
    """
    cursor = _collection().find({"release_date": {"$ne": None}}, {"release_date": 1})
    return {doc["_id"]: doc["release_date"] async for doc in cursor}


async def count() -> int:
    return await _collection().count_documents({})


async def replace_all(sets: list[dict]) -> int:
    """Escribe los sets con upsert, igual que el Pokédex.

    Upsert y no borrar-e-insertar: borrar deja una ventana en la que importar
    una lista fallaría entera.
    """
    if not sets:
        return 0

    result = await _collection().bulk_write(
        [UpdateOne({"_id": s["_id"]}, {"$set": s}, upsert=True) for s in sets],
        ordered=False,
    )
    return result.upserted_count + result.modified_count
