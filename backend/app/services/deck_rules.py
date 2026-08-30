"""Deck-construction rules for the Pokémon TCG.

Lives apart from the endpoints and the repository on purpose: `validate_deck` is a
pure function — it receives data, returns data, never touches the network or the
database — so it can be reasoned about and tested without starting anything up.
When the tests arrive in phase 5, this file will be the easiest one in the project
to cover.

Implemented rules:

  1. Exactly 60 cards.
  2. At most 4 copies with the same NAME. Two different printings of Iono count
     together: the rule is per name, not per card.
  3. Basic energy is exempt from the previous rule. A deck can carry twenty
     Lightning Energy.
  4. At most 1 ACE SPEC total. It is not "one per name": it is one per deck.
  5. Every card legal in the format the deck declares.

Not implemented, and worth knowing: the limit of 1 Radiant Pokémon per deck. It
would be caught the same way ACE SPEC is, by rarity.
"""

from collections import defaultdict

from app.models.card import Card, DeckFormat
from app.models.deck import (
    DECK_SIZE,
    MAX_ACE_SPEC,
    MAX_COPIES_PER_NAME,
    DeckCard,
    DeckValidation,
    Violation,
    ViolationCode,
)


def validate_deck(
    cards: list[DeckCard],
    catalogue: dict[str, Card],
    deck_format: DeckFormat,
) -> DeckValidation:
    """Checks a decklist against the format's rules.

    `catalogue` maps card_id -> Card, already resolved by the caller. It arrives
    already built instead of being looked up here so this function does not
    depend on the database: that is what keeps it pure and testable.
    """
    violations: list[Violation] = []

    # --- unknown card --------------------------------------------------------
    # First, because the rest of the rules need each card's data. It can genuinely
    # happen: a card that was synced with --format standard and later falls out
    # of the filter, or an id made up by a client.
    unknown = [entry.card_id for entry in cards if entry.card_id not in catalogue]
    if unknown:
        violations.append(
            Violation(
                code=ViolationCode.UNKNOWN_CARD,
                params={"count": len(unknown)},
                card_ids=unknown,
            )
        )

    known = [entry for entry in cards if entry.card_id in catalogue]

    # --- size ------------------------------------------------------------
    total = sum(entry.quantity for entry in cards)
    if total != DECK_SIZE:
        # `diff` is unsigned: the client picks "missing" or "too many" by
        # comparing `total` against `expected` itself, so it needs a magnitude,
        # not a sign it would have to strip back off.
        violations.append(
            Violation(
                code=ViolationCode.WRONG_SIZE,
                params={
                    "expected": DECK_SIZE,
                    "total": total,
                    "diff": abs(DECK_SIZE - total),
                },
            )
        )

    # --- 4 copies per name -----------------------------------------------
    # Grouped by name, not by card_id: "Iono" from one set and "Iono" from
    # another are the same card as far as the rulebook is concerned. That is why
    # the names have to be resolved, and why the catalogue arrives as a
    # parameter.
    by_name: dict[str, int] = defaultdict(int)
    ids_by_name: dict[str, list[str]] = defaultdict(list)

    for entry in known:
        card = catalogue[entry.card_id]
        if card.is_basic_energy:
            continue  # exempt
        by_name[card.name] += entry.quantity
        ids_by_name[card.name].append(entry.card_id)

    exceeded = {
        name: n for name, n in by_name.items() if n > MAX_COPIES_PER_NAME
    }
    for name, n in sorted(exceeded.items()):
        violations.append(
            Violation(
                code=ViolationCode.TOO_MANY_COPIES,
                params={"name": name, "count": n, "max": MAX_COPIES_PER_NAME},
                card_ids=ids_by_name[name],
            )
        )

    # --- ACE SPEC ----------------------------------------------------------
    ace_ids = [e.card_id for e in known if catalogue[e.card_id].is_ace_spec]
    ace_total = sum(e.quantity for e in known if catalogue[e.card_id].is_ace_spec)
    if ace_total > MAX_ACE_SPEC:
        violations.append(
            Violation(
                code=ViolationCode.TOO_MANY_ACE_SPEC,
                params={"count": ace_total, "max": MAX_ACE_SPEC},
                card_ids=ace_ids,
            )
        )

    # --- legality in the format -------------------------------------------
    illegal_ids = [
        entry.card_id
        for entry in known
        if not catalogue[entry.card_id].is_legal_in(deck_format)
    ]
    if illegal_ids:
        names = sorted({catalogue[cid].name for cid in illegal_ids})
        # English card names, which are data, not prose — they survive as a param.
        sample = ", ".join(names[:3]) + ("…" if len(names) > 3 else "")
        violations.append(
            Violation(
                code=ViolationCode.ILLEGAL_IN_FORMAT,
                params={
                    "count": len(illegal_ids),
                    "format": deck_format.value,
                    "sample": sample,
                },
                card_ids=illegal_ids,
            )
        )

    return DeckValidation(
        is_legal=not violations,
        total_cards=total,
        violations=violations,
    )
