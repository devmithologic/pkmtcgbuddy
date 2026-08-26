# Reprint Equivalence Key

> **Stack:** Python · **Introduced in:** Fixing legality propagation for Pokémon with rewrites and Trainer cards · **Date:** 2026-08-26

## Definition

A **reprint equivalence key** is a value that identifies which cards are considered "the same card" for the purposes of game rules. In Pokémon TCG, a single card can have multiple printings (reprints) across different sets, and the game's legality rules treat all reprints as equivalent — if one printing is legal, the others are too. The key determines which reprints group together. The key's calculation can depend on the **card category** (Pokémon, Trainer, Energy), because the game rules themselves differ by category.

## Why it exists

**The problem:** Boss's Orders is printed in four different sets with four different text versions:
- Swinging Strikes (mark D): `"Switch 1 of your opponent's Benched Pokémon with their Active Pokémon"`
- Scarlet & Violet (mark G): `"Switch in 1 of your opponent's Benched Pokémon to the Active Spot"`
- Paldea Evolved (mark I): `"Switch in 1 of your opponent's Benched Pokémon to the Active Spot"`

These are the same card, mechanically identical, just rewritten for clarity. If the mark I version is legal in Standard, the others are legal too.

TCGdex reports each as a separate legal status. Without propagating legality between reprints, a player building a deck with the mark G version (which exists in their collection) would be told it's illegal — because TCGdex says only mark I is legal. This is wrong.

But this rule applies **only to Trainers and Energies.** For Pokémon, a rewrite signals a real change:

- Pikachu in Base Set attacks with `Thunderbolt` (30 damage)
- Pikachu in Jungle attacks with `Thunderbolt` (40 damage)
- Pikachu in Fossil attacks with `Thunder Wave` (a different attack entirely)

These are functionally different cards. Grouping them by name and propagating legality would be wrong — only the legal version should be offered.

The solution: **use a different equivalence key for each category.** Pokémon group by identity (the full card signature: name, text, attacks), Trainers and Energies by name alone.

## How it works

When syncing cards, before writing them to the database, scan all documents to find which reprints are legal. Then propagate that legality to all reprints of the same card (by the category's equivalence key).

**Step 1: Decide the equivalence key for this card**
```python
import re

_SUFIJO_DE_ARTE = re.compile(r"\s*\([^)]*\)\s*$")
_CATEGORIAS_POR_NOMBRE = {"Trainer", "Energy"}

def _reprint_key(document: dict) -> str | None:
    """What counts as "the same card" depends on category."""
    if document.get("category") in _CATEGORIAS_POR_NOMBRE:
        # Name is the card. Strip art suffixes like "(Giovanni)".
        return "name:" + _SUFIJO_DE_ARTE.sub("", document["name"]).strip().lower()
    else:
        # For Pokémon, the complete signature (identity field).
        # Two Pikachu with different attacks are different cards.
        return document.get("identity")
```

**Step 2: Collect all legal reprints**
```python
def _apply_reprint_rule(documents: list[dict]) -> int:
    # Find all cards that are legal
    legales_std = set()
    legales_exp = set()
    for doc in documents:
        clave = _reprint_key(doc)
        if clave:
            if doc["legal_standard"]:
                legales_std.add(clave)  # This equivalence key is legal
            if doc["legal_expanded"]:
                legales_exp.add(clave)
```

**Step 3: Propagate legality to all reprints**
```python
    # Now mark all reprints of legal cards as legal
    for doc in documents:
        clave = _reprint_key(doc)
        if clave in legales_std:
            doc["legal_standard"] = True
        if clave in legales_exp:
            doc["legal_expanded"] = True
```

## In this project

**The implementation:**
```python
# backend/app/services/card_sync.py

# Pokémon: group by identity (content signature)
# Trainer, Energy: group by name
_CATEGORIAS_POR_NOMBRE = {"Trainer", "Energy"}

def _reprint_key(document: dict) -> str | None:
    """Qué cuenta como «la misma carta» al propagar legalidad.

    La clave depende de la CATEGORÍA, porque la regla del juego depende de la
    categoría:

    - **Pokémon: la huella completa** (`identity`). Dos Pikachu de sets distintos
      atacan distinto: son cartas diferentes, no reimpresiones.

    - **Trainer y Energy: el nombre.** El reglamento dice que una impresión
      antigua se juega CON EL TEXTO ACTUAL. Así que una diferencia de redacción
      no la convierte en otra carta.
    """
    if document.get("category") in _CATEGORIAS_POR_NOMBRE:
        return "name:" + _SUFIJO_DE_ARTE.sub("", document["name"]).strip().lower()
    return document.get("identity")
```

The measurement: Before this change, 25 different text versions of Boss's Orders (and 192 of its reprints across those versions) were treated as separate cards. After the change, they are recognized as one, and legality propagates correctly.

## Gotchas

**The equivalence key is specific to legality, not to search or display.** A user searching for "Pikachu" still sees all Pikachu, not just one representative. The key only affects which reprints are marked legal. This is intentional — the user may prefer a specific art version or a specific text version (if multiple are available).

**Removing the suffix requires care.** TCGdex adds parenthetical art identifiers like `Boss's Orders (Akari's Choice)` or `Boss's Orders (Giovanni)`. The parentheses are not part of the card's legal name — they are data about the illustrator. Stripping them correctly means: if two cards have the same name-without-parentheses, they are reprints. Failing to strip causes a card with art to be treated as a separate card from one without it.

**This rule only works because the sync sees the whole dataset.** The equivalence key function cannot live in the adapter (the layer that reads from TCGdex) because it translates one card at a time and never sees the others. Deciding "all Bosses Orders are the same" requires comparing across the full list. The sync job loads all 15,000+ cards into memory, applies the rule, then writes them. If it crashes halfway, re-running is safe — the rule is idempotent.

**Category matters.** A function that always uses identity (Pokémon's rule) would break Trainers. One that always uses name would break Pokémon. The category check is not a safety measure, it is the logic itself.

## Related concepts

The `identity` field used for Pokémon equivalence is calculated by `_identity()` in `backend/app/services/card_source.py:167` — it combines the card's name, text, and attack signatures to create a unique fingerprint.

See [`18_MONGODB_DENORMALIZATION_FOR_SORTING.md`](./18_MONGODB_DENORMALIZATION_FOR_SORTING.md) — after legality is propagated, the denormalized `set_release_date` field is used to decide which reprint appears first in search results.

## References

- [Pokémon TCG Rules: Reprinting and Legality](https://www.pokemon.com/us/pokemon-trading-card-game/play/rules/) — Official rules on how reprints are treated
- [TCGdex API: Card Model](https://tcgdex.dev/docs/api/model/card) — How card data is structured in the source
