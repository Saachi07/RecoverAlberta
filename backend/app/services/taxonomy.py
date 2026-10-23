"""Item taxonomy v1 and name lookup (inventory.md s5).

Source of truth is `app/data/taxonomy_v1.csv`, one row per leaf class, meant to
be reviewed in a spreadsheet by an insurance professional. Columns:

  id, name, group       identifiers
  claim_class           contents | building | unclear
  legacy_category       maps to the current Gemini category enum
  bulk, high_value      0/1 flags
  modifiers             1 if "built-in" / "freestanding" in the name can flip
                        the leaf's claim class
  aliases               pipe-separated phrases that map a free-text name here
  lifespan_years        empty until written with an insurance professional
  price_band_source     empty until pricing data is chosen
  reviewed              0 until a professional signs the row off

Matching is by whole tokens, not substrings, so "outdoor" does not hit "door",
"hair trimmer" does not hit "trim", and "filing cabinet" resolves to the filing
cabinet leaf instead of the generic "cabinet". The longest matching alias wins.
Nothing here is legal or coverage advice; claim_class values reproduce the
conventions the previous keyword list and prompt already used.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

TAXONOMY_PATH = Path(__file__).resolve().parent.parent / "data" / "taxonomy_v1.csv"

CLAIM_CLASSES = ("contents", "building", "unclear")

BUILDING_NOTE = (
    "Usually part of the building. Homeowners claim it under dwelling "
    "coverage; renters should report it to their landlord."
)
UNCLEAR_NOTE = (
    "Could be contents or part of the building. Ask your adjuster how to "
    "claim it."
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _singular(tok: str) -> str:
    # Applied to aliases and names alike, so it only has to be consistent.
    if len(tok) > 3 and tok.endswith("ies"):
        return tok[:-3] + "y"
    if len(tok) > 3 and tok.endswith("s") and not tok.endswith(("ss", "us", "is")):
        return tok[:-1]
    return tok


def tokenize(text: str) -> tuple[str, ...]:
    return tuple(_singular(t) for t in _TOKEN_RE.findall((text or "").lower()))


# Phrases in an item name that say how it is installed. Compared as token runs.
_BUILT_IN_MARKERS = tuple(
    tokenize(p)
    for p in ("built-in", "built in", "builtin", "wall mounted", "recessed", "integrated", "installed")
)
_FREESTANDING_MARKERS = tuple(
    tokenize(p)
    for p in ("freestanding", "free standing", "free-standing", "standalone", "portable", "countertop")
)


def _contains_run(tokens: tuple[str, ...], run: tuple[str, ...]) -> bool:
    n = len(run)
    return n > 0 and any(tokens[i : i + n] == run for i in range(len(tokens) - n + 1))


@dataclass(frozen=True)
class Leaf:
    id: str
    name: str
    group: str
    claim_class: str
    legacy_category: str
    bulk: bool
    high_value: bool
    modifiers: bool
    lifespan_years: Optional[float]
    price_band_source: str
    reviewed: bool
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class Match:
    leaf: Leaf
    alias: str
    score: tuple[int, int]  # (alias tokens, alias chars); higher wins


@lru_cache(maxsize=1)
def load_taxonomy(path: str = str(TAXONOMY_PATH)) -> tuple[Leaf, ...]:
    leaves: list[Leaf] = []
    seen: set[str] = set()
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            claim = row["claim_class"].strip()
            if claim not in CLAIM_CLASSES:
                raise ValueError(f"{row['id']}: bad claim_class {claim!r}")
            if row["id"] in seen:
                raise ValueError(f"duplicate taxonomy id {row['id']!r}")
            seen.add(row["id"])
            life = row.get("lifespan_years", "").strip()
            leaves.append(
                Leaf(
                    id=row["id"].strip(),
                    name=row["name"].strip(),
                    group=row["group"].strip(),
                    claim_class=claim,
                    legacy_category=row["legacy_category"].strip(),
                    bulk=row["bulk"].strip() == "1",
                    high_value=row["high_value"].strip() == "1",
                    modifiers=row["modifiers"].strip() == "1",
                    lifespan_years=float(life) if life else None,
                    price_band_source=row.get("price_band_source", "").strip(),
                    reviewed=row.get("reviewed", "0").strip() == "1",
                    aliases=tuple(a.strip() for a in row["aliases"].split("|") if a.strip()),
                )
            )
    return tuple(leaves)


@lru_cache(maxsize=1)
def _alias_index() -> tuple[tuple[tuple[str, ...], str, int, Leaf], ...]:
    """(alias tokens, alias text, leaf order, leaf), longest alias first."""
    entries = []
    for order, leaf in enumerate(load_taxonomy()):
        for alias in leaf.aliases:
            toks = tokenize(alias)
            if toks:
                entries.append((toks, alias, order, leaf))
    entries.sort(key=lambda e: (-len(e[0]), -sum(len(t) for t in e[0]), e[2]))
    return tuple(entries)


def _find_run(tokens: tuple[str, ...], run: tuple[str, ...]) -> int:
    """Index just past the last occurrence of run in tokens, or -1."""
    n = len(run)
    for i in range(len(tokens) - n, -1, -1):
        if tokens[i : i + n] == run:
            return i + n
    return -1


def match_name(name: str) -> Optional[Match]:
    """Best taxonomy leaf for a free-text item name, or None.

    Longest alias (in tokens) wins. Among equally long aliases, the one that
    appears later in the name wins, because the head noun comes last in
    English: "countertop microwave" is a microwave, not a countertop.
    Remaining ties go to alias length in characters, then taxonomy order.
    """
    tokens = tokenize(name)
    if not tokens:
        return None
    best = None
    best_key = None
    for toks, alias, order, leaf in _alias_index():
        end = _find_run(tokens, toks)
        if end < 0:
            continue
        chars = sum(len(t) for t in toks)
        key = (len(toks), end, chars, -order)
        if best_key is None or key > best_key:
            best, best_key = Match(leaf, alias, (len(toks), chars)), key
    return best


def get_leaf(leaf_id: str) -> Optional[Leaf]:
    return next((l for l in load_taxonomy() if l.id == leaf_id), None)


def note_for(claim_class: str) -> Optional[str]:
    if claim_class == "building":
        return BUILDING_NOTE
    if claim_class == "unclear":
        return UNCLEAR_NOTE
    return None


def resolve_claim_class(name: str) -> Optional[tuple[str, Optional[str], str]]:
    """(claim_class, note, leaf_id) from the taxonomy, or None if no leaf matches.

    "built-in" or similar in the name turns a modifier-sensitive leaf into
    building; "freestanding" or similar turns it into contents. A leaf that is
    already building or contents without the modifier flag is never flipped.
    """
    m = match_name(name)
    if m is None:
        return None
    claim = m.leaf.claim_class
    if m.leaf.modifiers:
        tokens = tokenize(name)
        if any(_contains_run(tokens, r) for r in _BUILT_IN_MARKERS):
            claim = "building"
        elif any(_contains_run(tokens, r) for r in _FREESTANDING_MARKERS):
            claim = "contents"
    return claim, note_for(claim), m.leaf.id
