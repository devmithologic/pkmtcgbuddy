"""What remains of the game model.

This file used to be the largest in the project and is now the smallest.
When games moved to live inside a session (see models/session.py), almost
everything that was here moved up a level: the date and the deck belong to
the session, not to the round.

What is left is what is genuinely a game's own —how it ended— and the two
date conversions between Python and BSON, which the session now uses.

A module shrinking when the domain is remodeled is not lost work: it is the
sign that the data was in the wrong place.
"""

from datetime import date, datetime, time, timezone
from enum import Enum


class MatchResult(str, Enum):
    """Result of a game.

    Inherits from str in addition to Enum so it serializes to JSON as "win"
    and not as an object. Using an Enum instead of free text means FastAPI
    rejects any other value with an automatic 422: free validation at the
    boundary.
    """

    WIN = "win"
    LOSS = "loss"
    TIE = "tie"


def date_to_bson(value: date) -> datetime:
    """Converts a date to what MongoDB knows how to store.

    BSON —MongoDB's binary format— has no "date without time" type. It only
    has datetime. Passing a Python `date` directly raises
    `InvalidDocument: cannot encode object: datetime.date`.

    It is stored at midnight UTC. The time is padding and means nothing;
    what matters is that the round trip back discards it, so as not to
    invent a precision the user never entered.
    """
    return datetime.combine(value, time.min, tzinfo=timezone.utc)


def date_from_bson(value: datetime) -> date:
    """The way back: trims the midnight padding."""
    return value.date()
