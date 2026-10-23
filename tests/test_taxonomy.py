"""Tests for taxonomy v1 (data integrity) and the name lookup that backs
classify_claim_class. Pure logic, no model calls."""

import sys
from collections import defaultdict
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

pytest.importorskip("pydantic")

from app.services.gemini_inventory import classify_claim_class  # noqa: E402
from app.services.taxonomy import (  # noqa: E402
    CLAIM_CLASSES,
    get_leaf,
    load_taxonomy,
    match_name,
    resolve_claim_class,
    tokenize,
)

LEGACY_CATEGORIES = {"furniture", "appliance", "electronics", "decor", "clothing", "other"}


class TestDataIntegrity:
    def test_loads_and_is_nonempty(self):
        assert len(load_taxonomy()) >= 100

    def test_ids_unique_and_fields_valid(self):
        ids = [l.id for l in load_taxonomy()]
        assert len(ids) == len(set(ids))
        for l in load_taxonomy():
            assert l.claim_class in CLAIM_CLASSES, l.id
            assert l.legacy_category in LEGACY_CATEGORIES, l.id
            assert l.aliases, f"{l.id} has no aliases"

    def test_no_alias_shared_between_leaves(self):
        seen = defaultdict(set)
        for l in load_taxonomy():
            for a in l.aliases:
                seen[tokenize(a)].add(l.id)
        clashes = {k: v for k, v in seen.items() if len(v) > 1}
        assert not clashes

    def test_every_alias_resolves_to_its_own_leaf(self):
        for l in load_taxonomy():
            for a in l.aliases:
                assert match_name(a).leaf.id == l.id, (l.id, a)

    def test_nothing_marked_reviewed_yet(self):
        # Flip this when a professional signs rows off; until then the data
        # must not claim a review that has not happened.
        assert not any(l.reviewed for l in load_taxonomy())

    def test_pending_professional_fields_left_empty(self):
        assert all(l.lifespan_years is None for l in load_taxonomy())


class TestTokenMatching:
    @pytest.mark.parametrize(
        "name, expected_leaf",
        [
            ("outdoor chair", "patio_set"),  # "door" inside "outdoor" must not match
            ("filing cabinet", "filing_cabinet"),  # not generic cabinet
            ("kitchen cabinets", "built_in_cabinets"),
            ("range hood", "range_hood"),  # longer alias beats "range"
            ("dishwasher", "dishwasher"),  # not "washer"
            ("door mat", "area_rug"),  # not "door"
            ("persian carpet", "area_rug"),  # not wall-to-wall carpet
            ("microwave oven", "microwave"),  # not generic oven
        ],
    )
    def test_longest_whole_token_wins(self, name, expected_leaf):
        assert match_name(name).leaf.id == expected_leaf

    def test_hair_trimmer_is_not_trim(self):
        assert match_name("hair trimmer") is None

    def test_plural_and_case_insensitive(self):
        assert match_name("Wooden DINING CHAIRS").leaf.id == "chair"

    def test_empty_and_none(self):
        assert match_name("") is None
        assert match_name(None) is None


class TestClaimClass:
    @pytest.mark.parametrize(
        "name, category, expected",
        [
            ("outdoor chair", "furniture", "contents"),
            ("filing cabinet", "furniture", "contents"),
            ("kitchen cabinets", "other", "building"),
            ("hair trimmer", "appliance", "unclear"),
            ("hair trimmer", "electronics", "contents"),
            ("built-in dishwasher", "appliance", "building"),
            ("dishwasher", "appliance", "unclear"),
            ("freestanding oven", "appliance", "contents"),
            ("wall oven", "appliance", "building"),
            ("countertop microwave", "appliance", "contents"),
            ("built in refrigerator", "appliance", "building"),
            ("stainless steel refrigerator", "appliance", "contents"),
            ("cabinet", "furniture", "unclear"),
            ("built-in cabinet", "furniture", "building"),
            ("front door", "other", "building"),
            ("shower curtain", "other", "contents"),
            ("shed", "other", "unclear"),
        ],
    )
    def test_cases(self, name, category, expected):
        assert classify_claim_class(name, category)[0] == expected

    def test_modifier_does_not_flip_building_leaf(self):
        assert resolve_claim_class("freestanding bathtub")[0] == "building"

    def test_notes_match_class(self):
        assert "building" in classify_claim_class("wallpaper", "other")[1].lower()
        assert "adjuster" in classify_claim_class("dishwasher", "appliance")[1].lower()
        assert classify_claim_class("sofa", "furniture")[1] is None

    def test_resolve_returns_leaf_id(self):
        assert resolve_claim_class("leather sofa")[2] == "sofa"
        assert get_leaf("sofa").group == "Seating"

    def test_unknown_item_falls_back_to_category(self):
        assert classify_claim_class("mystery gadget", "other")[0] == "unclear"
        assert classify_claim_class("mystery gadget", "electronics")[0] == "contents"
