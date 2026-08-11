"""Reglas de construcción de mazo del Pokémon TCG.

Vive aparte de los endpoints y del repositorio a propósito: `validate_deck` es una
función pura —recibe datos, devuelve datos, no toca red ni base— así que se puede
razonar y probar sin arrancar nada. Cuando lleguen los tests en la fase 5, este
fichero será el más fácil de cubrir del proyecto.

Reglas implementadas:

  1. Exactamente 60 cartas.
  2. Como mucho 4 copias con el mismo NOMBRE. Dos impresiones distintas de Iono
     cuentan juntas: la regla es por nombre, no por carta.
  3. La energía básica está exenta de la regla anterior. Un mazo puede llevar
     veinte Lightning Energy.
  4. Como mucho 1 ACE SPEC en total. No es "una por nombre": es una en el mazo.
  5. Todas las cartas legales en el formato declarado por el mazo.

No implementada, y conviene saberlo: el límite de 1 Pokémon Radiant por mazo. Se
detectaría igual que las ACE SPEC, por rareza.
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
    """Comprueba una lista contra las reglas del formato.

    `catalogue` mapea card_id -> Card, ya resuelto por quien llama. Se recibe hecho
    en lugar de consultarlo aquí para que esta función no dependa de la base: es
    lo que la mantiene pura y probable.
    """
    violations: list[Violation] = []

    # --- carta desconocida -------------------------------------------------
    # Primero, porque el resto de reglas necesitan los datos de cada carta. Puede
    # pasar de verdad: una carta que se sincronizó con --format standard y luego
    # desaparece del filtro, o un id inventado por un cliente.
    unknown = [entry.card_id for entry in cards if entry.card_id not in catalogue]
    if unknown:
        violations.append(
            Violation(
                code=ViolationCode.UNKNOWN_CARD,
                message=f"{len(unknown)} carta(s) no están en el catálogo sincronizado",
                card_ids=unknown,
            )
        )

    known = [entry for entry in cards if entry.card_id in catalogue]

    # --- tamaño ------------------------------------------------------------
    total = sum(entry.quantity for entry in cards)
    if total != DECK_SIZE:
        faltan = DECK_SIZE - total
        detalle = f"faltan {faltan}" if faltan > 0 else f"sobran {-faltan}"
        violations.append(
            Violation(
                code=ViolationCode.WRONG_SIZE,
                message=f"Un mazo son {DECK_SIZE} cartas: hay {total}, {detalle}",
            )
        )

    # --- 4 copias por nombre -----------------------------------------------
    # Se agrupa por nombre, no por card_id: "Iono" de un set y "Iono" de otro son
    # la misma carta para el reglamento. Por eso hace falta resolver los nombres,
    # y por eso el catálogo llega como parámetro.
    por_nombre: dict[str, int] = defaultdict(int)
    ids_por_nombre: dict[str, list[str]] = defaultdict(list)

    for entry in known:
        card = catalogue[entry.card_id]
        if card.is_basic_energy:
            continue  # exenta
        por_nombre[card.name] += entry.quantity
        ids_por_nombre[card.name].append(entry.card_id)

    excedidas = {
        nombre: n for nombre, n in por_nombre.items() if n > MAX_COPIES_PER_NAME
    }
    for nombre, n in sorted(excedidas.items()):
        violations.append(
            Violation(
                code=ViolationCode.TOO_MANY_COPIES,
                message=f"«{nombre}»: {n} copias, el máximo son {MAX_COPIES_PER_NAME}",
                card_ids=ids_por_nombre[nombre],
            )
        )

    # --- ACE SPEC ----------------------------------------------------------
    ace_ids = [e.card_id for e in known if catalogue[e.card_id].is_ace_spec]
    ace_total = sum(e.quantity for e in known if catalogue[e.card_id].is_ace_spec)
    if ace_total > MAX_ACE_SPEC:
        violations.append(
            Violation(
                code=ViolationCode.TOO_MANY_ACE_SPEC,
                message=(
                    f"{ace_total} cartas ACE SPEC: solo se permite "
                    f"{MAX_ACE_SPEC} por mazo"
                ),
                card_ids=ace_ids,
            )
        )

    # --- legalidad en el formato -------------------------------------------
    ilegales = [
        entry.card_id
        for entry in known
        if not catalogue[entry.card_id].is_legal_in(deck_format)
    ]
    if ilegales:
        nombres = sorted({catalogue[cid].name for cid in ilegales})
        muestra = ", ".join(nombres[:3]) + ("…" if len(nombres) > 3 else "")
        violations.append(
            Violation(
                code=ViolationCode.ILLEGAL_IN_FORMAT,
                message=(
                    f"{len(ilegales)} carta(s) no son legales en "
                    f"{deck_format.value}: {muestra}"
                ),
                card_ids=ilegales,
            )
        )

    return DeckValidation(
        is_legal=not violations,
        total_cards=total,
        violations=violations,
    )
