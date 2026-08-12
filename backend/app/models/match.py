"""Lo que queda del modelo de partida.

Este fichero era el más grande del proyecto y ahora es el más pequeño. Cuando las
partidas pasaron a vivir dentro de una sesión (ver models/session.py), casi todo
lo que había aquí subió un nivel: la fecha y el mazo son de la sesión, no de la
ronda.

Queda lo genuinamente propio de una partida —cómo terminó— y las dos conversiones
de fecha entre Python y BSON, que ahora usa la sesión.

Que un módulo encoja al remodelar el dominio no es pérdida de trabajo: es la señal
de que los datos estaban en el sitio equivocado.
"""

from datetime import date, datetime, time, timezone
from enum import Enum


class MatchResult(str, Enum):
    """Resultado de una partida.

    Hereda de str además de Enum para que se serialice a JSON como "win" y no como
    un objeto. Usar un Enum en lugar de texto libre significa que FastAPI rechaza
    cualquier otro valor con un 422 automático: validación gratis en el borde.
    """

    WIN = "win"
    LOSS = "loss"
    TIE = "tie"


def date_to_bson(value: date) -> datetime:
    """Convierte una fecha a lo que MongoDB sabe guardar.

    BSON —el formato binario de MongoDB— no tiene tipo "fecha sin hora". Solo
    tiene datetime. Pasar un `date` de Python directamente lanza
    `InvalidDocument: cannot encode object: datetime.date`.

    Se guarda a medianoche UTC. La hora es relleno y no significa nada; lo que
    importa es que la vuelta atrás la descarte, para no inventar una precisión que
    el usuario nunca introdujo.
    """
    return datetime.combine(value, time.min, tzinfo=timezone.utc)


def date_from_bson(value: datetime) -> date:
    """La vuelta: recorta el relleno de medianoche."""
    return value.date()
