"""Tests for validation of the inventory evidence fields (migration 0012)."""

import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

pytest.importorskip("pydantic")

from app.services.item_fields import (  # noqa: E402
    BASE_FIELDS,
    DAMAGE_TYPES,
    EXTRA_FIELDS,
    WRITABLE,
    clean_item_row,
)

MIGRATION = BACKEND / "supabase" / "migrations" / "0012_inventory_extras.sql"


def ok(data):
    row, problem = clean_item_row(data)
    assert problem is None, problem
    return row


def bad(data, fragment):
    row, problem = clean_item_row(data)
    assert row == {}
    assert problem and fragment in problem


class TestPassthrough:
    def test_unknown_keys_dropped(self):
        row = ok({"name": "sofa", "user_id": "x", "id": "y", "evil": 1})
        assert row == {"name": "sofa"}

    def test_old_payload_unchanged(self):
        payload = {"name": "sofa", "category": "furniture", "estimated_value": 450,
                   "confidence": 0.8, "room": "living_room"}
        assert ok(payload) == payload

    def test_writable_is_union(self):
        assert WRITABLE == BASE_FIELDS | EXTRA_FIELDS
        assert not BASE_FIELDS & EXTRA_FIELDS


class TestPrice:
    def test_range_ok(self):
        row = ok({"name": "tv", "price_low": 300, "price_high": 500.5,
                  "price_basis": "acv", "price_date": "2026-10-21"})
        assert row["price_low"] == 300

    @pytest.mark.parametrize("field", ["price_low", "price_high"])
    @pytest.mark.parametrize("value", [-1, "12", True, 10**9])
    def test_bad_price(self, field, value):
        bad({"name": "x", field: value}, field)

    def test_low_above_high(self):
        bad({"name": "x", "price_low": 9, "price_high": 3}, "cannot be greater")

    def test_single_bound_allowed(self):
        ok({"name": "x", "price_high": 3})

    def test_basis_and_date(self):
        bad({"name": "x", "price_basis": "market"}, "price_basis")
        bad({"name": "x", "price_date": "21/10/2026"}, "price_date")

    def test_none_clears(self):
        row = ok({"name": "x", "price_low": None, "price_basis": None})
        assert row["price_low"] is None


class TestClassFields:
    def test_claim_class(self):
        ok({"name": "x", "claim_class": "building"})
        bad({"name": "x", "claim_class": "maybe"}, "claim_class")

    def test_taxonomy_id_must_exist(self):
        ok({"name": "x", "taxonomy_id": "sofa"})
        bad({"name": "x", "taxonomy_id": "flying_carpet"}, "taxonomy_id")
        bad({"name": "x", "taxonomy_id": 5}, "taxonomy_id")

    def test_bulk(self):
        assert ok({"name": "x", "bulk": True})["bulk"] is True
        bad({"name": "x", "bulk": "yes"}, "bulk")

    def test_bulk_null_is_ignored_not_cleared(self):
        assert "bulk" not in ok({"name": "x", "bulk": None})

    def test_damage_types_sorted_and_deduped(self):
        row = ok({"name": "x", "damage_types": ["soot", "smoke", "soot"]})
        assert row["damage_types"] == ["smoke", "soot"]

    def test_damage_types_rules(self):
        bad({"name": "x", "damage_types": ["lava"]}, "unknown damage type")
        bad({"name": "x", "damage_types": ["none", "smoke"]}, "none")
        bad({"name": "x", "damage_types": "smoke"}, "list")
        assert "none" in DAMAGE_TYPES


class TestComparables:
    GOOD = {"name": "IKEA Kivik sofa", "source": "ikea.ca", "price": 899,
            "currency": "CAD", "date": "2026-10-01", "url": "https://example.com/p"}

    def test_good(self):
        assert ok({"name": "x", "comparables": [self.GOOD]})["comparables"] == [self.GOOD]

    def test_unknown_keys_dropped(self):
        row = ok({"name": "x", "comparables": [{**self.GOOD, "secret": 1}]})
        assert "secret" not in row["comparables"][0]

    @pytest.mark.parametrize(
        "comp, fragment",
        [
            ({"price": 5}, "name"),
            ({"name": "a", "price": -5}, "price"),
            ({"name": "a", "date": "yesterday"}, "date"),
            ({"name": "a", "url": "javascript:alert(1)"}, "url"),
            ({"name": "a", "currency": "CADX"}, "currency"),
            ("not a dict", "object"),
        ],
    )
    def test_bad(self, comp, fragment):
        bad({"name": "x", "comparables": [comp]}, fragment)

    def test_too_many_and_not_list(self):
        bad({"name": "x", "comparables": [self.GOOD] * 11}, "at most")
        bad({"name": "x", "comparables": {"a": 1}}, "list")


class TestConfidenceEvidenceSource:
    def test_field_confidence(self):
        ok({"name": "x", "field_confidence": {"class": 0.9, "price": 0.4}})
        bad({"name": "x", "field_confidence": {"class": 1.2}}, "between 0 and 1")
        bad({"name": "x", "field_confidence": {"class": "high"}}, "between 0 and 1")
        bad({"name": "x", "field_confidence": [0.5]}, "object")

    def test_evidence_ok_and_filtered(self):
        row = ok({"name": "x", "evidence": {
            "photo_url": "https://e/x.jpg", "photo_index": 2,
            "bounding_box": {"x1": 0.1, "y1": 0.1, "x2": 0.5, "y2": 0.9}, "junk": 1}})
        assert "junk" not in row["evidence"]

    @pytest.mark.parametrize(
        "ev",
        [
            {"bounding_box": {"x1": 0.5, "y1": 0.1, "x2": 0.2, "y2": 0.9}},
            {"bounding_box": {"x1": 0, "y1": 0, "x2": 2, "y2": 1}},
            {"bounding_box": {"x1": 0, "y1": 0}},
            {"photo_index": -1},
            {"photo_index": True},
            "box",
        ],
    )
    def test_evidence_bad(self, ev):
        bad({"name": "x", "evidence": ev}, "evidence")

    def test_source(self):
        ok({"name": "x", "source": "gemini-2.5-flash"})
        bad({"name": "x", "source": "  "}, "source")
        bad({"name": "x", "source": "a" * 101}, "source")


class TestMigrationMatchesCode:
    def test_every_extra_field_has_a_column(self):
        sql = MIGRATION.read_text()
        for f in EXTRA_FIELDS:
            assert f"add column if not exists {f}" in sql, f

    def test_migration_check_values_match_code(self):
        sql = MIGRATION.read_text()
        for v in ("replacement", "acv", "contents", "building", "unclear"):
            assert f"'{v}'" in sql
