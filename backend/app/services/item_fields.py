"""Validation for the inventory evidence fields added in migration 0012.

Pure functions, no Flask or Supabase, so the rules are unit-testable. The items
blueprint calls `clean_item_row` on every create and update: it keeps only
writable keys and rejects malformed evidence fields with a message the client
can show, instead of letting a bad value reach a database constraint.

None is always accepted for the new fields (it clears them on PATCH).
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Optional

from .taxonomy import CLAIM_CLASSES, get_leaf

PRICE_BASES = ("replacement", "acv")

# inventory.md s7. Multi-label; "none" stands alone.
DAMAGE_TYPES = (
    "smoke", "soot", "char", "heat_warping", "water_stain", "standing_water",
    "flood_mud", "mold", "impact_dent", "wind_debris", "freeze_burst", "none",
)

BASE_FIELDS = frozenset({
    "name", "category", "material", "estimated_value", "damage_type",
    "damage_severity", "confidence", "image_url", "before_url", "after_url",
    "receipts", "description", "room", "purchase_date", "case_id",
})

EXTRA_FIELDS = frozenset({
    "price_low", "price_high", "price_basis", "price_date", "comparables",
    "field_confidence", "taxonomy_id", "claim_class", "bulk", "damage_types",
    "evidence", "source",
})

WRITABLE = BASE_FIELDS | EXTRA_FIELDS

_MAX_PRICE = 10_000_000
_MAX_COMPARABLES = 10
_COMPARABLE_KEYS = ("name", "source", "price", "currency", "date", "url")
_EVIDENCE_KEYS = ("photo_url", "photo_index", "bounding_box")
_BOX_KEYS = ("x1", "y1", "x2", "y2")


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _is_iso_date(v: Any) -> bool:
    if not isinstance(v, str):
        return False
    try:
        _dt.date.fromisoformat(v)
        return True
    except ValueError:
        return False


def _price(field: str, v: Any) -> Optional[str]:
    if not _is_num(v) or v < 0 or v > _MAX_PRICE:
        return f"{field} must be a number between 0 and {_MAX_PRICE}"
    return None


def _comparables(v: Any) -> tuple[Any, Optional[str]]:
    if not isinstance(v, list):
        return None, "comparables must be a list"
    if len(v) > _MAX_COMPARABLES:
        return None, f"comparables can hold at most {_MAX_COMPARABLES} entries"
    cleaned = []
    for c in v:
        if not isinstance(c, dict):
            return None, "each comparable must be an object"
        name = c.get("name")
        if not isinstance(name, str) or not name.strip() or len(name) > 200:
            return None, "each comparable needs a name (200 characters or fewer)"
        out: dict[str, Any] = {"name": name.strip()}
        if "price" in c and c["price"] is not None:
            err = _price("comparable price", c["price"])
            if err:
                return None, err
            out["price"] = c["price"]
        for key, limit in (("source", 100), ("currency", 3), ("url", 500)):
            val = c.get(key)
            if val is None:
                continue
            if not isinstance(val, str) or len(val) > limit:
                return None, f"comparable {key} must be text of {limit} characters or fewer"
            if key == "url" and not val.startswith(("http://", "https://")):
                return None, "comparable url must start with http:// or https://"
            out[key] = val
        if c.get("date") is not None:
            if not _is_iso_date(c["date"]):
                return None, "comparable date must be YYYY-MM-DD"
            out["date"] = c["date"]
        cleaned.append(out)
    return cleaned, None


def _field_confidence(v: Any) -> Optional[str]:
    if not isinstance(v, dict) or len(v) > 16:
        return "field_confidence must be an object with at most 16 fields"
    for k, val in v.items():
        if not isinstance(k, str) or not k or len(k) > 32:
            return "field_confidence keys must be short text"
        if not _is_num(val) or not 0 <= val <= 1:
            return f"field_confidence[{k!r}] must be a number between 0 and 1"
    return None


def _evidence(v: Any) -> tuple[Any, Optional[str]]:
    if not isinstance(v, dict):
        return None, "evidence must be an object"
    out: dict[str, Any] = {}
    for key in _EVIDENCE_KEYS:
        if key not in v or v[key] is None:
            continue
        val = v[key]
        if key == "photo_url":
            if not isinstance(val, str) or len(val) > 1000:
                return None, "evidence.photo_url must be text of 1000 characters or fewer"
        elif key == "photo_index":
            if not isinstance(val, int) or isinstance(val, bool) or not 0 <= val < 1000:
                return None, "evidence.photo_index must be a whole number"
        elif key == "bounding_box":
            if not isinstance(val, dict) or set(val) != set(_BOX_KEYS):
                return None, "evidence.bounding_box needs x1, y1, x2, y2"
            if not all(_is_num(val[k]) and 0 <= val[k] <= 1 for k in _BOX_KEYS):
                return None, "evidence.bounding_box values must be between 0 and 1"
            if val["x1"] >= val["x2"] or val["y1"] >= val["y2"]:
                return None, "evidence.bounding_box must have x1 < x2 and y1 < y2"
        out[key] = val
    return out, None


def clean_item_row(data: dict) -> tuple[dict, Optional[str]]:
    """Keep writable keys and validate the evidence fields.

    Returns (row, None) on success or ({}, message) on the first problem.
    """
    row = {k: v for k, v in data.items() if k in WRITABLE}

    for f in ("price_low", "price_high"):
        if row.get(f) is not None:
            err = _price(f, row[f])
            if err:
                return {}, err
    low, high = row.get("price_low"), row.get("price_high")
    if low is not None and high is not None and low > high:
        return {}, "price_low cannot be greater than price_high"

    if row.get("price_basis") is not None and row["price_basis"] not in PRICE_BASES:
        return {}, "price_basis must be 'replacement' or 'acv'"

    if row.get("price_date") is not None and not _is_iso_date(row["price_date"]):
        return {}, "price_date must be YYYY-MM-DD"

    if row.get("claim_class") is not None and row["claim_class"] not in CLAIM_CLASSES:
        return {}, "claim_class must be contents, building, or unclear"

    if "bulk" in row and row["bulk"] is not None and not isinstance(row["bulk"], bool):
        return {}, "bulk must be true or false"
    if "bulk" in row and row["bulk"] is None:
        del row["bulk"]  # column is NOT NULL; null means "leave it alone"

    tid = row.get("taxonomy_id")
    if tid is not None and (not isinstance(tid, str) or get_leaf(tid) is None):
        return {}, "taxonomy_id is not a known taxonomy class"

    dt = row.get("damage_types")
    if dt is not None:
        if not isinstance(dt, list) or len(dt) > len(DAMAGE_TYPES):
            return {}, "damage_types must be a list"
        bad = [d for d in dt if d not in DAMAGE_TYPES]
        if bad:
            return {}, f"unknown damage type: {bad[0]!r}"
        if "none" in dt and len(dt) > 1:
            return {}, "damage_types 'none' cannot be combined with other types"
        row["damage_types"] = sorted(set(dt))

    if row.get("comparables") is not None:
        row["comparables"], err = _comparables(row["comparables"])
        if err:
            return {}, err

    if row.get("field_confidence") is not None:
        err = _field_confidence(row["field_confidence"])
        if err:
            return {}, err

    if row.get("evidence") is not None:
        row["evidence"], err = _evidence(row["evidence"])
        if err:
            return {}, err

    src = row.get("source")
    if src is not None and (not isinstance(src, str) or not src.strip() or len(src) > 100):
        return {}, "source must be text of 100 characters or fewer"

    return row, None
