"""Agregaciones sobre `sessions`.

Aquí vive el *aggregation pipeline*, que es la herramienta de MongoDB para
responder preguntas que `find()` no puede: contar, agrupar, cruzar colecciones.
Funciona como una tubería — cada etapa recibe los documentos de la anterior y
entrega los suyos a la siguiente.

La tubería de este módulo hace esto:

    $match   quedarse solo con las sesiones de este mazo y del periodo pedido
    $unwind  una sesión con 5 rondas se convierte en 5 documentos, uno por ronda
    $facet   calcular VARIOS agrupamientos distintos sobre esos mismos documentos

`$unwind` es la clave de que las partidas estén embebidas: convierte el array en
filas, y a partir de ahí se agrupa como si cada ronda fuera un documento suelto.

`$facet` es lo que evita recorrer los datos cuatro veces. Sin él harían falta
cuatro consultas —global, por versión, por rival, por tipo de evento— cada una
releyendo las mismas sesiones. Con `$facet`, una sola lectura alimenta las
cuatro ramas.
"""

from datetime import date

from bson import ObjectId

from app.db.mongo import get_database
from app.models.match import date_to_bson
from app.models.session import SessionType

# Se repite en las cuatro ramas del $facet, así que se construye una vez.
# $cond dentro de $sum es el equivalente a "cuenta 1 si se cumple, 0 si no":
# MongoDB no tiene un COUNT(*) FILTER como SQL, se emula así.
_COUNTERS = {
    "wins": {"$sum": {"$cond": [{"$eq": ["$matches.result", "win"]}, 1, 0]}},
    "losses": {"$sum": {"$cond": [{"$eq": ["$matches.result", "loss"]}, 1, 0]}},
    "ties": {"$sum": {"$cond": [{"$eq": ["$matches.result", "tie"]}, 1, 0]}},
}


async def deck_stats(
    version_ids: list[ObjectId],
    date_from: date | None = None,
    date_to: date | None = None,
    session_type: SessionType | None = None,
) -> dict:
    """Agrega las partidas de un mazo, cortadas de cuatro formas.

    `version_ids` son TODAS las versiones del mazo: una sesión referencia una
    versión concreta, así que para las estadísticas del mazo entero hay que
    reunirlas. Quien llama las resuelve, para que este módulo no dependa del
    repositorio de mazos.
    """
    if not version_ids:
        return {"overall": [], "by_version": [], "by_archetype": [], "by_session_type": [], "sessions": 0}

    filtro: dict = {"deck_version_id": {"$in": version_ids}}

    if date_from or date_to:
        rango = {}
        if date_from:
            rango["$gte"] = date_to_bson(date_from)
        if date_to:
            # $lte y no $lt: date_to es inclusivo, y las fechas se guardan a
            # medianoche, así que el día completo entra.
            rango["$lte"] = date_to_bson(date_to)
        filtro["played_at"] = rango

    if session_type:
        filtro["session_type"] = session_type.value

    coleccion = get_database()["sessions"]

    # Las sesiones se cuentan en una consulta aparte, no dentro de la tubería.
    #
    # El intento natural era meter un $facet con dos ramas —contar sesiones por
    # un lado, desdoblar y agrupar por otro— pero MongoDB lo rechaza:
    #
    #     $facet is not allowed to be used within a $facet stage
    #
    # No se pueden anidar. Y hacerlo después de $unwind daría partidas en vez de
    # sesiones, porque para entonces cada ronda ya es un documento. Dos consultas
    # es la salida honesta, y la segunda es un contador con índice.
    total_sesiones = await coleccion.count_documents(filtro)

    pipeline = [
        {"$match": filtro},
        # Convierte una sesión de 5 rondas en 5 documentos, uno por ronda. Es lo
        # que permite agrupar partidas estando embebidas.
        {"$unwind": "$matches"},
        {
            "$facet": {
                "overall": [{"$group": {"_id": None, **_COUNTERS}}],
                "by_version": [
                    {"$group": {"_id": "$deck_version_id", **_COUNTERS}}
                ],
                "by_archetype": [
                    {"$group": {"_id": "$matches.opponent_archetype", **_COUNTERS}},
                    # Más partidas primero: un matchup de 8 dice más que uno de 1,
                    # y conviene que se lea antes.
                    {"$sort": {"wins": -1, "losses": -1, "_id": 1}},
                ],
                "by_session_type": [
                    {"$group": {"_id": "$session_type", **_COUNTERS}}
                ],
            }
        },
    ]

    cursor = await coleccion.aggregate(pipeline)
    resultado = [doc async for doc in cursor]
    ramas = resultado[0] if resultado else {}

    return {
        "sessions": total_sesiones,
        "overall": ramas.get("overall", []),
        "by_version": ramas.get("by_version", []),
        "by_archetype": ramas.get("by_archetype", []),
        "by_session_type": ramas.get("by_session_type", []),
    }
