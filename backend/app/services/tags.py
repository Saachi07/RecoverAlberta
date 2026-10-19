"""Map raw intake answers to semantic tags used by the content filter.

Adapted from the ``questions`` branch, kept as a pure function so it can
be reused by both the case-write path (which persists ``derived_tags``) and
the recommender (which mixes them into the query vector).
"""

from __future__ import annotations


def derive_tags(intake_answers: dict) -> set[str]:
    tags: set[str] = set()

    housing = intake_answers.get("housing")
    if housing in (0, 1):
        tags.add("owner")
    if housing in (2, 3):
        tags.add("renter")
    if housing in (1, 3):
        tags.add("displaced")
    if housing == 4:
        tags.add("on_reserve_or_metis")
        # Optional follow-up shown only to this group: which community, so we
        # can route to the right pathway (band/ISC, Métis settlement, Inuit).
        community = intake_answers.get("indigenous_community")
        if community == 0:
            tags.add("first_nation_reserve")
        elif community == 1:
            tags.add("metis_settlement")
        elif community == 2:
            tags.add("inuit_community")
    if housing == 5:
        tags.add("needs_shelter")
        tags.add("displaced")

    ins = intake_answers.get("insurance")
    if ins == 0:
        tags.add("insured")
    if ins == 1:
        tags.add("uninsured")
    if ins == 2:
        tags.add("insurance_unknown")

    income = intake_answers.get("income_affected")
    if income in (1, 2):
        tags.add("income_disrupted")
    if income == 3:
        tags.add("on_assistance")

    applied = intake_answers.get("already_applied")
    if applied in (1, 3):
        tags.add("insurance_claim_filed")
    if applied in (2, 3):
        tags.add("aid_applied")
    if applied == 0:
        tags.add("not_yet_started")

    if intake_answers.get("has_kids"):
        tags.add("has_kids")
    if intake_answers.get("has_seniors"):
        tags.add("has_seniors")
    if intake_answers.get("has_disability"):
        tags.add("has_disability")
    if intake_answers.get("has_pets"):
        tags.add("has_pets")
    if intake_answers.get("has_id") == 0:
        tags.add("missing_id")

    return tags
