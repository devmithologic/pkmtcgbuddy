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

from pymongo import ASCENDING, DESCENDING, UpdateOne

from app.db.mongo import get_database
from app.models.card import (
    Card,
    CardCategory,
    CardSearchResult,
    CardSummary,
    DeckFormat,
)

COLLECTION = "cards"

# La rareza de una impresión normal. Las energías básicas se reimprimen también
# como secretas —"Hyper rare", "Ultra Rare"—, que son la misma carta con adornos.
PLAIN_RARITY = "Common"


def _collection():
    return get_database()[COLLECTION]


def set_id_of(card_id: str) -> str:
    """El id del set al que pertenece una carta: `me01-077` -> `me01`.

    rpartition y NUNCA split: 21 ids de set llevan guiones dentro
    (`tk-ex-latia`), así que partir por el primero devolvería `tk` y la carta se
    quedaría sin fecha. Es la misma trampa que ya documenta deck_text.py.
    """
    return card_id.rpartition("-")[0]


def sort_name(name: str, is_basic_energy: bool) -> str:
    """El nombre por el que se ordena, que no siempre es el nombre.

    TCGdex llama `Metal Energy` a la energía básica normal y `Basic Metal Energy`
    a la secreta dorada. Son la misma carta, pero ordenando por nombre la dorada
    gana SIEMPRE por alfabeto, da igual lo que digan la fecha o la rareza: la «B»
    va antes que la «M». Quitando el prefijo, las dos caen en el mismo grupo y el
    desempate lo decide `printing_rank`.

    Solo para las básicas. `Basic Research Note` no es la reimpresión de ninguna
    `Research Note`, y recortarle el prefijo la mandaría a otro sitio de la lista.
    """
    bajo = name.lower()
    if is_basic_energy and bajo.startswith("basic "):
        return bajo.removeprefix("basic ")
    return bajo


def search_name(name: str, is_basic_energy: bool) -> str:
    """El texto contra el que busca el filtro, que no siempre es el nombre.

    A una energía básica se le antepone «basic», aunque su impresión no lo lleve.
    El motivo es que las dos formas del nombre circulan: la carta vigente se
    llama `Metal Energy` en TCGdex, pero quien construye un mazo la busca —y la
    escribe en una lista— como *basic Metal Energy*. Sin esto, teclear «basic»
    encontraba únicamente las ocho secretas doradas, que son las únicas ocho que
    llevan la palabra en el nombre.

    Anteponer, y no guardar las dos formas por separado, funciona porque la
    búsqueda es por subcadena: «basic metal energy» CONTIENE «metal energy», así
    que un solo campo responde a las dos maneras de escribirlo.
    """
    if is_basic_energy:
        return f"basic {sort_name(name, True)}"
    return name.lower()


def printing_rank(is_basic_energy: bool, rarity: str | None) -> int:
    """0 para una impresión normal, 1 para una secreta. Solo mira las básicas.

    Acotado a las energías básicas a propósito. En una carta de verdad, cuál de
    sus impresiones metes en el mazo es una decisión legítima —el arte importa, y
    quien busca `Boss's Orders` quiere ver las suyas— así que degradar las
    especiales reordenaría el buscador entero por una preferencia que nadie ha
    pedido. En una energía básica no hay decisión: es la misma carta con mejor
    foto, y lo que hace falta es que la normal se pueda encontrar.
    """
    if is_basic_energy and rarity != PLAIN_RARITY:
        return 1
    return 0


async def ensure_indexes() -> None:
    """Crea los índices que necesitan las búsquedas.

    Sin índice, cada consulta recorre la colección entera (*collection scan*).
    Con ~20.000 cartas eso son milisegundos y no se nota; el hábito importa
    igualmente, porque el día que no se note ya será tarde.

    create_index es idempotente: si el índice existe, no hace nada. Por eso se
    puede llamar en cada arranque sin comprobar antes.
    """
    collection = _collection()
    # Compuesto, y EXACTAMENTE en el orden en que se ordena en search_cards. Un
    # índice solo sirve para ordenar si sus campos y sus direcciones coinciden
    # con el sort; si no coinciden, Mongo trae los documentos y los ordena en
    # memoria, con un tope de 32 MB a partir del cual la consulta falla.
    await collection.create_index(
        [
            ("sort_name", ASCENDING),
            ("printing_rank", ASCENDING),
            ("set_release_date", DESCENDING),
            ("_id", ASCENDING),
        ]
    )
    # El de identity lo usa la sustitución de imagen: sin él, cada página de
    # resultados con una carta sin imagen recorrería la colección entera.
    await collection.create_index([("identity", ASCENDING)])
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
        # Los dos campos por los que se ORDENA. Se guardan calculados por lo
        # mismo que name_lower: derivarlos en tiempo de consulta impediría que
        # ningún índice ayudase, y ordenar sin índice es ordenar en memoria.
        "sort_name": sort_name(card.name, card.is_basic_energy),
        "search_name": search_name(card.name, card.is_basic_energy),
        "printing_rank": printing_rank(card.is_basic_energy, card.rarity),
        "image_url": card.image_url,
        "category": card.category.value,
        "rarity": card.rarity,
        "regulation_mark": card.regulation_mark,
        "legal_standard": card.legal_standard,
        "legal_expanded": card.legal_expanded,
        "is_ace_spec": card.is_ace_spec,
        "is_basic_energy": card.is_basic_energy,
        "identity": card.identity,
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
        identity=document.get("identity", ""),
    )


def _build_filter(
    name: str | None,
    deck_format: DeckFormat | None,
    category: CardCategory | None,
    ace_spec_only: bool,
) -> dict:
    """Traduce los filtros del dominio a una consulta de MongoDB."""
    # De cada energía básica se ofrece UNA impresión, no las 27. Va en el filtro
    # y no en el orden porque son problemas distintos: ordenar decide cuál sale
    # primero de las que entran, y aquí lo que hace falta es que las demás no
    # entren. Buscar "basic" enseñaba ocho energías doradas de coleccionista
    # justamente por esto — eran las únicas ocho cuyo NOMBRE lleva la palabra, y
    # ningún orden puede rescatar a una carta que el filtro ya descartó.
    #
    # $ne y no False: los documentos escritos antes de que el campo existiera no
    # lo tienen, y "no lo tiene" significa que se ofrece.
    query: dict = {"is_energy_duplicate": {"$ne": True}}

    if name:
        # $regex sin anclar reproduce el comportamiento de TCGdex: subcadena, no
        # prefijo. "rod" encuentra "Aerodactyl".
        #
        # re.escape es obligatorio: sin él, un usuario que teclee "(" o "*"
        # provoca una expresión inválida, y patrones como "(a+)+" son un vector
        # de denegación de servicio por backtracking catastrófico (ReDoS).
        import re

        # Contra search_name y no contra name_lower: es el mismo texto salvo en
        # las energías básicas, donde lleva delante el «basic» que su impresión
        # puede no tener. Ver search_name().
        query["search_name"] = {"$regex": re.escape(name.lower())}

    if category:
        query["category"] = category.value

    if ace_spec_only:
        query["is_ace_spec"] = True

    if deck_format:
        query[f"legal_{deck_format.value}"] = True

    return query


async def _borrowed_images(documents: list[dict]) -> dict[str, str]:
    """{card_id: url} para las cartas sin imagen, prestada por una reimpresión.

    TCGdex no tiene imagen para 1035 de nuestras 15021 cartas, y entre ellas
    está el set `sve` ENTERO —las 24 energías básicas vigentes—. Comprobado
    contra su API, no deducido: `/cards/sve-008` devuelve `image: null`, y las 24
    igual. No es un fallo nuestro y no lo podemos arreglar en el origen.

    Pero 566 de esas 1035 tienen una reimpresión que sí tiene imagen, y una
    reimpresión es LA MISMA CARTA: mismo texto, mismo todo salvo el arte. Se le
    toma prestada la suya.

    Cuál se elige importa: entre las hermanas de `sve-008` hay una Ultra Rare de
    Crown Zenith, y usarla devolvería a la pantalla exactamente la energía
    recargada que este cambio quita. Por eso se ordena con el mismo criterio que
    el buscador —primero las normales, y entre ellas la más nueva—.

    `identity` es la huella que ya calcula card_source para la regla de
    reimpresión (ver card_sync._apply_reprint_rule): mismo concepto, cobrado por
    segunda vez.

    Se deriva al leer y NO se guarda. Guardar la URL prestada sería copiar en 566
    documentos un dato que pertenece a otro y que caduca en cuanto salga una
    impresión nueva — la misma decisión que ya está tomada para los sprites de
    Pokémon, vista desde el otro lado.

    Cuesta UNA consulta por página, no una por carta: se juntan las identidades
    que faltan y se piden todas juntas.
    """
    identidades = {
        doc["identity"]
        for doc in documents
        if not doc.get("image_url") and doc.get("identity")
    }
    if not identidades:
        return {}

    cursor = _collection().find(
        {"identity": {"$in": list(identidades)}, "image_url": {"$ne": None}},
        {"identity": 1, "image_url": 1, "printing_rank": 1, "set_release_date": 1},
    )

    mejor: dict[str, dict] = {}
    async for candidata in cursor:
        actual = mejor.get(candidata["identity"])
        if actual is None or _es_mejor_impresion(candidata, actual):
            mejor[candidata["identity"]] = candidata

    return {
        doc["_id"]: mejor[doc["identity"]]["image_url"]
        for doc in documents
        if not doc.get("image_url") and doc.get("identity") in mejor
    }


def _es_mejor_impresion(candidata: dict, actual: dict) -> bool:
    """¿La candidata es "más la carta" que la actual?

    Tres criterios, los mismos y en el mismo orden que usa el buscador: primero
    una impresión normal antes que una secreta, luego la más nueva, y el id para
    desempatar. Las fechas son "YYYY-MM-DD", así que compararlas como cadenas ya
    es compararlas como fechas.

    Se usa para dos cosas distintas que resultan ser la misma pregunta: de qué
    reimpresión copiar una imagen que falta, y cuál de las 27 impresiones de
    Metal Energy es la que ofrece el buscador.
    """
    rank_c = candidata.get("printing_rank", 0)
    rank_a = actual.get("printing_rank", 0)
    if rank_c != rank_a:
        return rank_c < rank_a

    # Sin fecha pierde: una carta sin datar no puede ser "la más nueva".
    fecha_c = candidata.get("set_release_date") or ""
    fecha_a = actual.get("set_release_date") or ""
    if fecha_c != fecha_a:
        return fecha_c > fecha_a

    # El desempate por id no es cosmético: sin él, cuál gana depende del orden en
    # que Mongo devuelva los documentos, y dos ejecuciones podrían elegir
    # impresiones distintas.
    return candidata["_id"] < actual["_id"]


def energy_duplicates(documents: list[dict]) -> set[str]:
    """Los ids de las impresiones de energía básica que el buscador NO ofrece.

    De las 322 impresiones de energía básica que hay sincronizadas, el selector
    de cartas enseña una por tipo: la normal más reciente. Las otras 313 siguen
    en la base y se resuelven perfectamente por id —un mazo que ya tenga dentro
    la dorada de SFA la sigue viendo— pero no se ofrecen al construir.

    Por qué las energías básicas y no todas las cartas: en una carta de verdad,
    cuál de sus impresiones metes es una decisión legítima y el arte importa, así
    que el buscador enseña las suyas. En una energía básica no hay decisión, son
    la misma carta, y ofrecer 27 Metal Energy no es dar a elegir: es esconder la
    que sirve entre 26 que no aportan nada.

    Recibe TODOS los documentos y no consulta nada, porque «la más reciente» solo
    se puede saber mirando el conjunto. Por eso este cálculo no puede vivir en
    card_to_document, que ve una carta cada vez.
    """
    mejores: dict[str, dict] = {}
    basicas: list[dict] = []

    for doc in documents:
        if not doc.get("is_basic_energy"):
            continue
        basicas.append(doc)
        actual = mejores.get(doc["sort_name"])
        if actual is None or _es_mejor_impresion(doc, actual):
            mejores[doc["sort_name"]] = doc

    ganadores = {doc["_id"] for doc in mejores.values()}
    return {doc["_id"] for doc in basicas if doc["_id"] not in ganadores}


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
        .find(query, {"name": 1, "image_url": 1, "identity": 1})
        # Cuatro claves, y cada una arregla un problema distinto:
        #
        #   sort_name         agrupa `Basic Metal Energy` con `Metal Energy`
        #   printing_rank     las secretas de una básica, después de las normales
        #   set_release_date  entre impresiones normales, gana la más nueva
        #   _id               desempate final, ver abajo
        #
        # Las tres primeras son la respuesta a que buscar «metal» devolviera
        # arriba del todo una energía dorada de coleccionista y ninguna normal
        # visible: la dorada ganaba por alfabeto y las 26 normales salían por
        # orden de id, así que la primera era de 1999.
        #
        # El _id final no es cosmético.
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
        .sort(
            [
                ("sort_name", ASCENDING),
                ("printing_rank", ASCENDING),
                ("set_release_date", DESCENDING),
                ("_id", ASCENDING),
            ]
        )
        .skip(skip)
        .limit(page_size + 1)
    )

    documents = [doc async for doc in cursor]
    has_more = len(documents) > page_size

    pagina = documents[:page_size]
    prestadas = await _borrowed_images(pagina)

    return CardSearchResult(
        cards=[
            CardSummary(
                id=doc["_id"],
                name=doc["name"],
                image_url=doc.get("image_url") or prestadas.get(doc["_id"]),
            )
            for doc in pagina
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
    if not document:
        return None

    carta = card_from_document(document)
    if not carta.image_url:
        # La ficha de una carta es donde más se nota que falte la imagen, y aquí
        # la consulta extra solo ocurre cuando de verdad falta.
        carta.image_url = (await _borrowed_images([document])).get(card_id)
    return carta


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
    documents = [doc async for doc in cursor]

    # La misma sustitución que en el buscador, y hace falta aquí también: esta
    # es la consulta que pinta la rejilla del mazo, así que sin ella una energía
    # ya guardada seguiría saliendo sin imagen aunque el buscador la enseñara.
    prestadas = await _borrowed_images(documents)

    cartas = {}
    for doc in documents:
        carta = card_from_document(doc)
        if not carta.image_url:
            carta.image_url = prestadas.get(doc["_id"])
        cartas[doc["_id"]] = carta
    return cartas


def _derived(document: dict, dates: dict[str, str]) -> dict:
    """Los campos de orden de una carta, calculados desde lo que ya está guardado.

    Existe para que las dos pasadas del rellenado calculen exactamente lo mismo:
    la primera necesita `sort_name` y `printing_rank` para decidir qué impresión
    de cada energía se ofrece, y la segunda los vuelve a necesitar para
    escribirlos. Duplicar el cálculo en los dos sitios es cómo se acaba con dos
    reglas que divergen.
    """
    basica = document.get("is_basic_energy", False)
    return {
        "_id": document["_id"],
        "is_basic_energy": basica,
        "sort_name": sort_name(document["name"], basica),
        "search_name": search_name(document["name"], basica),
        "printing_rank": printing_rank(basica, document.get("rarity")),
        "set_release_date": dates.get(set_id_of(document["_id"])),
    }


async def restamp_sort_fields(
    dates: dict[str, str], batch_size: int
) -> tuple[int, int]:
    """Recalcula `sort_name`, `printing_rank` y `set_release_date` en todas las
    cartas ya guardadas. Devuelve (escritas, cuántas se quedaron sin fecha).

    Lo llama el trabajo por lotes `card_sync.resort()`. Vive aquí y no allí
    porque es una operación sobre la colección de cartas de principio a fin: la
    única pieza que viene de fuera es el diccionario de fechas, que es de otra
    colección y por eso se recibe como argumento en vez de consultarse.

    Se proyectan solo los tres campos que hacen falta para calcular: traer 15021
    documentos enteros para leerles el nombre sería mover megabytes por gusto.

    Son DOS pasadas porque `is_energy_duplicate` no se puede decidir carta a
    carta: para saber si esta Metal Energy es la que se ofrece hay que haber
    visto las otras 26. La primera pasada mira solo las energías básicas —322
    documentos— y la segunda escribe.
    """
    collection = _collection()

    basicas = [
        _derived(doc, dates)
        async for doc in collection.find(
            {"is_basic_energy": True}, {"name": 1, "rarity": 1, "is_basic_energy": 1}
        )
    ]
    duplicadas = energy_duplicates(basicas)

    cursor = collection.find({}, {"name": 1, "rarity": 1, "is_basic_energy": 1})

    operaciones: list[UpdateOne] = []
    escritas = 0
    sin_fecha = 0

    async for doc in cursor:
        campos = _derived(doc, dates)
        if not campos["set_release_date"]:
            sin_fecha += 1

        operaciones.append(
            UpdateOne(
                {"_id": doc["_id"]},
                {
                    "$set": {
                        "sort_name": campos["sort_name"],
                        "search_name": campos["search_name"],
                        "printing_rank": campos["printing_rank"],
                        "set_release_date": campos["set_release_date"],
                        "is_energy_duplicate": doc["_id"] in duplicadas,
                    }
                },
            )
        )

        # En lotes por lo mismo que el sync: una escritura por carta son 15021
        # viajes de red, y acumularlo todo para escribir al final significa
        # perderlo entero si algo falla a mitad.
        if len(operaciones) >= batch_size:
            await collection.bulk_write(operaciones, ordered=False)
            escritas += len(operaciones)
            operaciones = []

    if operaciones:
        await collection.bulk_write(operaciones, ordered=False)
        escritas += len(operaciones)

    return escritas, sin_fecha


async def legality_snapshot() -> list[dict]:
    """Lo mínimo de cada carta para reaplicar la regla de reimpresión sin red.

    Cinco campos de 15021 documentos. La regla necesita ver el conjunto entero
    —una impresión es legal por lo que sean las OTRAS— así que no hay forma de
    hacerlo carta a carta ni en streaming.
    """
    cursor = _collection().find(
        {},
        {
            "name": 1,
            "category": 1,
            "identity": 1,
            "legal_standard": 1,
            "legal_expanded": 1,
        },
    )
    return [doc async for doc in cursor]


async def save_legality(documents: list[dict], batch_size: int) -> int:
    """Guarda `legal_standard` y `legal_expanded` de los documentos que se pasen.

    Recibe solo los que cambiaron, no los 15021: quien aplica la regla sabe
    cuáles tocó y escribir los demás sería reescribir el valor que ya tenían.
    """
    if not documents:
        return 0

    collection = _collection()
    escritas = 0
    for start in range(0, len(documents), batch_size):
        lote = documents[start : start + batch_size]
        await collection.bulk_write(
            [
                UpdateOne(
                    {"_id": doc["_id"]},
                    {
                        "$set": {
                            "legal_standard": doc["legal_standard"],
                            "legal_expanded": doc["legal_expanded"],
                        }
                    },
                )
                for doc in lote
            ],
            ordered=False,
        )
        escritas += len(lote)
    return escritas


async def count_cards() -> int:
    """Cuántas cartas hay sincronizadas. Sirve para distinguir «no hay
    resultados» de «nunca se ha sincronizado», que son problemas distintos."""
    return await _collection().count_documents({})
