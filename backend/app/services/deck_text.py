"""El formato de texto con el que se intercambian listas de mazo.

Es el que exporta PTCG Live y el que aceptan Limitless y el resto de
constructores de la red, así que es el formato de interoperabilidad de facto:

    Pokémon: 17
    3 Riolu PRE 50
    3 Mega Lucario ex MEG 77

    Trainer: 33
    4 Lillie's Determination MEG 119

    Energy: 10
    7 Fighting Energy MEE 6

Cada línea es `<cantidad> <nombre> <ABREVIATURA> <número>`. Las cabeceras de
categoría llevan su total y son informativas: la categoría real de una carta la
sabe el catálogo, así que se leen y se descartan — creer a la cabecera nos haría
importar como Trainer una carta que el usuario colocó en la sección equivocada.

Sin E/S ni framework, igual que `deck_rules.py`: aquí solo se pasa de texto a
estructura y al revés. Resolver las cartas contra el catálogo es trabajo del
router, que sí tiene base de datos.
"""

import re
from dataclasses import dataclass

# `3 Mega Lucario ex MEG 77`
#   cantidad · nombre (perezoso, puede llevar espacios) · abreviatura · número
#
# La abreviatura es de letras y dígitos —hay sets como `sv10.5w` cuyo código es
# `WHT`, pero también promos tipo `SVP`— y el número puede no ser solo dígitos:
# existen `TG01` y `SV001`. Anclar al final de la línea es lo que permite que el
# nombre contenga espacios sin ambigüedad.
LINEA = re.compile(
    r"^\s*(\d+)\s+(.+?)\s+([A-Za-z][A-Za-z0-9]{1,5})\s+([A-Za-z]*\d+[A-Za-z]*)\s*$"
)

# `Pokémon: 17`, `Trainer: 33`, `Energy: 10`, y sus variantes en otros idiomas o
# sin el total.
CABECERA = re.compile(r"^\s*[A-Za-zÀ-ÿ\s]+:\s*\d*\s*$")


@dataclass(frozen=True)
class ParsedLine:
    """Una línea de carta ya troceada, todavía sin resolver."""

    quantity: int
    name: str
    set_code: str
    number: str
    raw: str


def normalize_number(number: str) -> str:
    """Quita los ceros a la izquierda del tramo numérico final.

    Es la diferencia que hace que la mitad de una lista no se encuentre. TCGdex
    guarda `me01-077`; el formato de texto escribe `MEG 77`. Comparar las
    cadenas tal cual falla en toda carta cuyo número tenga menos de tres cifras,
    que son la mayoría.

    Se conserva el prefijo de letras porque hay números que no son solo dígitos:
    `TG01` -> `TG1`, `SV001` -> `SV1`.
    """
    m = re.match(r"^(.*?)(\d+)$", number)
    if not m:
        return number.upper()
    prefijo, digitos = m.groups()
    return f"{prefijo.upper()}{int(digitos)}"


def candidate_ids(set_id: str, number: str) -> list[str]:
    """Los ids que podría tener esa carta en el catálogo.

    En vez de guardar un número normalizado en las 15.000 cartas —que obligaría
    a resincronizarlas— se generan las variantes de relleno y se buscan todas de
    una vez con un `$in`. Una consulta para la lista entera, no una por línea.
    """
    m = re.match(r"^(.*?)(\d+)$", number)
    if not m:
        return [f"{set_id}-{number}"]

    prefijo, digitos = m.groups()
    n = int(digitos)
    # dict.fromkeys y no set: quita duplicados —un número de dos cifras da lo
    # mismo con relleno 1 y 2— conservando el orden, que hace el $in legible al
    # depurar.
    return list(
        dict.fromkeys(f"{set_id}-{prefijo}{n:0{ancho}d}" for ancho in (1, 2, 3, 4))
    )


def parse(text: str) -> tuple[list[ParsedLine], list[str]]:
    """Trocea el texto. Devuelve (líneas de carta, líneas no reconocidas).

    Las cabeceras y las líneas en blanco no cuentan como fallo: se descartan en
    silencio porque son parte del formato. Lo que se devuelve como no reconocido
    es lo que parecía una carta y no encajó, para poder enseñárselo al usuario
    tal como lo escribió.
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


# Orden y etiquetas de las secciones al exportar. El formato las espera en este
# orden y con estos nombres en inglés, que es lo que leen las demás
# herramientas: traducirlas rompería la interoperabilidad, que es todo el punto.
SECCIONES = [("Pokemon", "Pokémon"), ("Trainer", "Trainer"), ("Energy", "Energy")]


def render(entries: list[dict]) -> str:
    """Compone el texto a partir de las cartas ya resueltas.

    Cada entrada: {quantity, name, category, set_code, number}. Una carta sin
    `set_code` —de un set sin abreviatura oficial— se escribe igualmente con su
    nombre y cantidad: la lista resultante no será importable tal cual en otra
    herramienta, pero perder la carta al exportar sería peor que dar una línea
    que el usuario puede corregir.
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
