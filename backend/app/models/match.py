"""Modelos de una partida.

Dos modelos para un mismo concepto. Es el patrón DTO (Data Transfer Object): la
forma que viaja por la API no es la misma que la que se guarda en la base.

- MatchCreate: lo que el cliente ENVÍA. No lleva id ni created_at, porque esos los
  decide el servidor. Si el modelo de entrada los aceptara, un cliente podría
  inventarse un id o falsear la fecha de creación.
- MatchOut: lo que el servidor DEVUELVE. Lleva ambos.

Mezclar los dos en una sola clase es el error habitual, y solo se nota cuando ya
es caro arreglarlo.

Además, este módulo concentra la traducción entre "objeto Python" y "documento
BSON", que no son lo mismo. Ver match_to_document / match_from_document.
"""

from datetime import date, datetime, time, timezone
from enum import Enum

from bson import ObjectId
from pydantic import BaseModel, Field


class MatchResult(str, Enum):
    """Resultado de la partida.

    Hereda de str además de Enum para que se serialice a JSON como "win" y no como
    un objeto. Usar un Enum en lugar de texto libre significa que FastAPI rechaza
    cualquier otro valor con un 422 automático: validación gratis en el borde.
    """

    WIN = "win"
    LOSS = "loss"
    TIE = "tie"


class MatchCreate(BaseModel):
    """Datos que envía el cliente al registrar una partida."""

    played_at: date

    # LA idea central del proyecto: una partida se atribuye a la VERSIÓN jugada,
    # no solo al mazo. Sin esto, "el Mega Lucario gana el 60%" mezcla resultados
    # de listas distintas y no dice nada útil.
    #
    # Opcional porque una partida puede registrarse sin mazo propio —un torneo
    # con mazo prestado, o simplemente antes de haber construido la lista— y
    # porque las partidas que ya existían no lo tienen.
    #
    # Se guarda SOLO el id de versión, no también el del mazo. El mazo se deduce
    # de la versión: duplicarlo daría dos campos que pueden contradecirse, y
    # resolverlo al leer cuesta un $lookup.
    deck_version_id: str | None = None
    # Texto libre por ahora. En la fase 2 pasa a ser una referencia a Archetype,
    # una lista controlada: las estadísticas necesitan que "Gardevoir ex" y
    # "gardevoir" sean el mismo valor.
    opponent_archetype: str = Field(min_length=1, max_length=100)
    result: MatchResult
    notes: str | None = Field(default=None, max_length=1000)


class MatchOut(MatchCreate):
    """Datos que devuelve el servidor: los de MatchCreate más los que genera él."""

    id: str
    created_at: datetime

    # Resueltos al leer para que la interfaz pueda mostrar "Mega Lucario v2" sin
    # pedir el mazo aparte. Son None si la partida no tiene versión asociada, o
    # si el mazo se borró.
    deck_name: str | None = None
    deck_version: int | None = None


def match_to_document(match: MatchCreate) -> dict:
    """Convierte el modelo de entrada en un documento listo para insertar.

    Hay una conversión que no es cosmética: BSON —el formato binario de MongoDB—
    no tiene tipo "fecha sin hora". Solo tiene datetime. Pasar un date de Python
    directamente lanza InvalidDocument: cannot encode object: datetime.date.

    Así que guardamos la fecha como datetime a medianoche UTC. La hora es relleno
    y no significa nada; lo que importa es que la vuelta atrás (en
    match_from_document) descarte esa parte para no inventarse una precisión que
    el usuario nunca introdujo.
    """
    return {
        "played_at": datetime.combine(match.played_at, time.min, tzinfo=timezone.utc),
        "opponent_archetype": match.opponent_archetype,
        # .value convierte el Enum en la cadena "win". Guardar el objeto Enum
        # tampoco es codificable en BSON.
        "result": match.result.value,
        "notes": match.notes,
        "created_at": datetime.now(timezone.utc),
        # Se guarda como ObjectId, no como cadena: así el $lookup contra
        # deck_versions funciona sin conversiones, y Mongo puede indexarlo.
        "deck_version_id": (
            ObjectId(match.deck_version_id) if match.deck_version_id else None
        ),
    }


def match_from_document(document: dict, deck: dict | None = None) -> MatchOut:
    """Convierte un documento de MongoDB en la respuesta de la API.

    Dos traducciones, ambas obligatorias:

    1. Mongo guarda la clave primaria en _id y su tipo es ObjectId, que no es
       serializable a JSON. Devolverlo tal cual provoca un 500 al responder.
    2. played_at vuelve como datetime; lo recortamos a date, que es lo que el
       modelo declara y lo que el usuario introdujo.

    Se hace aquí, explícito y en un solo sitio, en vez de con un serializador
    global. Así el mecanismo se ve, y si mañana cambiamos de base de datos solo
    hay que tocar estas dos funciones.
    """
    version_id = document.get("deck_version_id")

    return MatchOut(
        id=str(document["_id"]),
        played_at=document["played_at"].date(),
        opponent_archetype=document["opponent_archetype"],
        result=document["result"],
        notes=document.get("notes"),
        created_at=document["created_at"],
        deck_version_id=str(version_id) if version_id else None,
        deck_name=(deck or {}).get("name"),
        deck_version=(deck or {}).get("version"),
    )
