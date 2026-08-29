"""Aggregations over `sessions`.

This is where the *aggregation pipeline* lives, MongoDB's tool for answering
questions `find()` can't: counting, grouping, joining collections. It works
like a pipe — each stage receives the previous stage's documents and hands its
own to the next one.

This module's pipeline does the following:

    $match   keep only the sessions for this deck and the requested period
    $unwind  a session with 5 rounds becomes 5 documents, one per round
    $facet   compute SEVERAL different groupings over those same documents

`$unwind` is the key to the games being embedded: it turns the array into
rows, and from there grouping proceeds as if each round were its own document.

`$facet` is what avoids scanning the data four times. Without it, four
separate queries would be needed — overall, by version, by opponent, by event
type — each one re-reading the same sessions. With `$facet`, a single read
feeds all four branches.
"""

from datetime import date

from bson import ObjectId

from app.db.mongo import get_database
from app.models.match import date_to_bson
from app.models.session import SessionType

# Repeated across the four branches of the $facet, so it's built once.
# $cond inside $sum is the equivalent of "count 1 if this holds, 0 if not":
# MongoDB has no COUNT(*) FILTER like SQL, so it's emulated this way.
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
    tag: str | None = None,
) -> dict:
    """Aggregates a deck's games, sliced four ways.

    `version_ids` are ALL of the deck's versions: a session references one
    specific version, so getting stats for the whole deck means gathering all
    of them. The caller resolves them, so this module doesn't depend on the
    deck repository.
    """
    if not version_ids:
        return {"overall": [], "by_version": [], "by_archetype": [], "by_session_type": [], "sessions": 0}

    filter_: dict = {"deck_version_id": {"$in": version_ids}}

    if date_from or date_to:
        range_ = {}
        if date_from:
            range_["$gte"] = date_to_bson(date_from)
        if date_to:
            # $lte and not $lt: date_to is inclusive, and dates are stored at
            # midnight, so the entire day is included.
            range_["$lte"] = date_to_bson(date_to)
        filter_["played_at"] = range_

    if session_type:
        filter_["session_type"] = session_type.value

    # Equality against an array: matches if the session contains that tag.
    if tag:
        filter_["tags"] = tag

    collection = get_database()["sessions"]

    # Sessions are counted in a separate query, not inside the pipeline.
    #
    # The natural attempt was to put a $facet with two branches — count
    # sessions on one side, unwind and group on the other — but MongoDB
    # rejects it:
    #
    #     $facet is not allowed to be used within a $facet stage
    #
    # They can't be nested. And doing it after $unwind would give games
    # instead of sessions, because by then each round is already its own
    # document. Two queries is the honest way out, and the second one is a
    # count backed by an index.
    # Sessions with no rounds are excluded. The $unwind below discards them
    # anyway, so counting them here would give "3 sessions" next to totals
    # drawn from just one — and with zero rounds, "0-0-0 across 3 sessions",
    # which reads like a bug.
    total_sessions = await collection.count_documents({**filter_, "matches": {"$ne": []}})

    pipeline = [
        {"$match": filter_},
        # Turns a session with 5 rounds into 5 documents, one per round. This
        # is what allows grouping games while they're embedded.
        {"$unwind": "$matches"},
        {
            "$facet": {
                "overall": [{"$group": {"_id": None, **_COUNTERS}}],
                "by_version": [
                    {"$group": {"_id": "$deck_version_id", **_COUNTERS}}
                ],
                "by_archetype": [
                    {"$group": {"_id": "$matches.opponent_archetype", **_COUNTERS}},
                    # Most games first: a matchup of 8 says more than one of 1,
                    # and it's worth reading before it.
                    {"$sort": {"wins": -1, "losses": -1, "_id": 1}},
                ],
                "by_session_type": [
                    {"$group": {"_id": "$session_type", **_COUNTERS}}
                ],
            }
        },
    ]

    cursor = await collection.aggregate(pipeline)
    result = [doc async for doc in cursor]
    branches = result[0] if result else {}

    return {
        "sessions": total_sessions,
        "overall": branches.get("overall", []),
        "by_version": branches.get("by_version", []),
        "by_archetype": branches.get("by_archetype", []),
        "by_session_type": branches.get("by_session_type", []),
    }
