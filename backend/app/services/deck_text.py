"""The text format decklists are exchanged in.

It is the one PTCG Live exports and the one Limitless and the rest of the
network's deck builders accept, so it is the de facto interoperability format:

    Pokémon: 17
    3 Riolu PRE 50
    3 Mega Lucario ex MEG 77

    Trainer: 33
    4 Lillie's Determination MEG 119

    Energy: 10
    7 Fighting Energy MEE 6

Each line is `<quantity> <name> <ABBREVIATION> <number>`. Category headers carry
their own total and are informational: a card's real category is known by the
catalogue, so they are read and discarded — trusting the header would let us
import as Trainer a card the user placed in the wrong section.

No I/O and no framework, same as `deck_rules.py`: this only turns text into a
structure and back. Resolving the cards against the catalogue is the router's
job, since it is the one with a database.
"""

import re
from dataclasses import dataclass

# `3 Mega Lucario ex MEG 77`
#   quantity · name (lazy, may contain spaces) · abbreviation · number
#
# The abbreviation is letters and digits — there are sets like `sv10.5w` whose
# code is `WHT`, but also promos like `SVP` — and the number may not be digits
# only: `TG01` and `SV001` exist. Anchoring to the end of the line is what lets
# the name contain spaces without ambiguity.
LINEA = re.compile(
    r"^\s*(\d+)\s+(.+?)\s+([A-Za-z][A-Za-z0-9]{1,5})\s+([A-Za-z]*\d+[A-Za-z]*)\s*$"
)

# `Pokémon: 17`, `Trainer: 33`, `Energy: 10`, and their variants in other
# languages or without the total.
CABECERA = re.compile(r"^\s*[A-Za-zÀ-ÿ\s]+:\s*\d*\s*$")


@dataclass(frozen=True)
class ParsedLine:
    """A card line already split apart, not yet resolved."""

    quantity: int
    name: str
    set_code: str
    number: str
    raw: str


def normalize_number(number: str) -> str:
    """Strips the leading zeros from the trailing numeric run.

    This is the difference that keeps half a list from being found. TCGdex
    stores `me01-077`; the text format writes `MEG 77`. Comparing the strings
    as-is fails on every card whose number has fewer than three digits, which
    is most of them.

    The letter prefix is kept because some numbers are not digits only:
    `TG01` -> `TG1`, `SV001` -> `SV1`.
    """
    m = re.match(r"^(.*?)(\d+)$", number)
    if not m:
        return number.upper()
    prefijo, digitos = m.groups()
    return f"{prefijo.upper()}{int(digitos)}"


def candidate_ids(set_id: str, number: str) -> list[str]:
    """The ids that card could have in the catalogue.

    Instead of storing a normalized number on the 15,000 cards — which would
    force resyncing them all — the padded variants are generated and looked up
    all at once with an `$in`. One query for the whole list, not one per line.
    """
    m = re.match(r"^(.*?)(\d+)$", number)
    if not m:
        return [f"{set_id}-{number}"]

    prefijo, digitos = m.groups()
    n = int(digitos)
    # dict.fromkeys, not set: it drops duplicates — a two-digit number gives the
    # same result with padding 1 and 2 — while keeping order, which makes the
    # $in readable when debugging.
    return list(
        dict.fromkeys(f"{set_id}-{prefijo}{n:0{ancho}d}" for ancho in (1, 2, 3, 4))
    )


def parse(text: str) -> tuple[list[ParsedLine], list[str]]:
    """Splits the text apart. Returns (card lines, unrecognized lines).

    Headers and blank lines do not count as a failure: they are silently
    dropped because they are part of the format. What comes back as
    unrecognized is what looked like a card and did not fit, so it can be
    shown to the user exactly as they wrote it.
    """
    lineas: list[ParsedLine] = []
    sueltas: list[str] = []

    for bruta in text.splitlines():
        if not bruta.strip() or CABECERA.match(bruta):
            continue

        m = LINEA.match(bruta)
        if not m:
            sueltas.append(bruta.strip())
            continue

        cantidad, nombre, codigo, numero = m.groups()
        lineas.append(
            ParsedLine(
                quantity=int(cantidad),
                name=nombre.strip(),
                set_code=codigo.upper(),
                number=numero,
                raw=bruta.strip(),
            )
        )

    return lineas, sueltas


# Order and labels of the sections when exporting. The format expects them in
# this order and with these English names, which is what the other tools
# read: translating them would break the interoperability that is the whole
# point.
SECCIONES = [("Pokemon", "Pokémon"), ("Trainer", "Trainer"), ("Energy", "Energy")]


def render(entries: list[dict]) -> str:
    """Composes the text from cards that are already resolved.

    Each entry: {quantity, name, category, set_code, number}. A card with no
    `set_code` — from a set with no official abbreviation — is still written
    out with its name and quantity: the resulting list will not be importable
    as-is in another tool, but dropping the card on export would be worse than
    giving a line the user can fix.
    """
    bloques = []

    for clave, etiqueta in SECCIONES:
        grupo = [e for e in entries if e["category"] == clave]
        if not grupo:
            continue

        total = sum(e["quantity"] for e in grupo)
        lineas = [f"{etiqueta}: {total}"]
        for e in grupo:
            codigo = e.get("set_code")
            numero = e.get("number")
            sufijo = f" {codigo} {numero}" if codigo and numero else ""
            lineas.append(f"{e['quantity']} {e['name']}{sufijo}")
        bloques.append("\n".join(lineas))

    return "\n\n".join(bloques) + "\n" if bloques else ""
