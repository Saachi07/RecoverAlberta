"""Content-based filtering recommender.

This is the primary recommendation engine. It is pure content-based: every
recommendation is justified by feature overlap between the user's case (a
"profile vector") and a resource's metadata (an "item vector"). No
collaborative signal (clicks, ratings, neighbour-similarity) is used.

Pipeline
--------
1. **Build the case query.** Concatenate the case's disaster type, region,
   derived tags, plus the categories / damage descriptors of every item the
   user has logged. This is the textual representation of the user's
   situation.
2. **Eligibility filter (hard where it must be, soft where it can be).**
   Drop resources whose ``region``, ``disaster_types``, ``excludes`` tags,
   or ``eligibility_days`` window make them clearly inapplicable. A
   resource's ``requires`` tags are softer: tags come from photos and
   documents the user may simply not have uploaded yet, so a missing tag
   means "unknown", not "ineligible". Those resources stay in with a score
   penalty and a "worth double-checking" reason; only a resource whose
   requirements contradict everything we know is dropped.
3. **TF-IDF cosine similarity (soft).** Vectorize the survivors'
   ``search_text`` with TF-IDF, vectorize the query the same way, and score
   each survivor by cosine similarity. This is the content-based core.
   The fitted vectorizer is cached per resource corpus so repeat requests
   only pay for the query transform.
4. **Small structured boosts.** Insurer match, tag-overlap depth, deadline
   pressure, and a losses-versus-coverage comparison are added on top of
   the cosine score as interpretable bonuses.
5. **Normalize.** Final scores are scaled to [0, 1] within the request so
   the UI can show meaningful "strong / good / worth a look" labels instead
   of raw unbounded numbers. Done and dismissed resources are pushed below
   zero after normalization so they sink to the bottom without vanishing.
6. **Per-category top-K.** Group by resource ``type`` so the UI gets a
   diverse output (a row of shelters, a row of financial programs, etc.)
   instead of all shelters because the case is recent.

The output is a list of ``Recommendation`` dataclasses, each carrying a
score, the persisted status, and a list of human-readable reasons for the
"Suggested because: ..." UI copy. All user-facing copy here stays warm and
avoids dashes per product voice.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Iterable, Optional

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .signals import DocumentDeadline, DocumentSignals, InventorySignals

# Weights are interpretable and hand-tuned. Replace with a learned ranker
# once enough feedback data (saved / dismissed / acted-on) accumulates;
# impressions and status changes are logged by the recommendations
# blueprint for exactly that purpose.
W_CONTENT = 2.5  # scaled so typical cosine values compete with the boosts
W_TAG_OVERLAP = 0.4
W_INSURER = 0.8
W_FRESHNESS = 0.1
W_URGENCY = 0.5
W_DEADLINE = 0.7
W_VALUE = 0.4
PENALTY_UNCONFIRMED = 0.3   # requires tags we can't confirm yet
# Applied after normalization (scores are in [0, 1] by then), so these
# reliably push completed / dismissed resources to the bottom.
PENALTY_DONE = 1.0
PENALTY_DISMISSED = 2.0

# Resource types where an extracted document deadline (claim window, DRP
# application date) is actually actionable; shelters don't care.
_DEADLINE_TYPES = {"insurance", "financial", "policy", "legal", "documents"}

# Route extracted deadlines to the resource types they belong to, instead
# of letting one receipt deadline inflate every insurance and legal
# resource identically. Matched against the deadline's label + source doc.
_DEADLINE_ROUTES: list[tuple[re.Pattern[str], set[str]]] = [
    (re.compile(r"claim|insur|policy|proof of loss|adjuster", re.I), {"insurance", "policy"}),
    (re.compile(r"applic|assist|drp|grant|fund|benefit", re.I), {"financial"}),
    (re.compile(r"appeal|dispute|respond|ombud|legal", re.I), {"legal"}),
    (re.compile(r"replace|renew|passport|licen|id\b", re.I), {"documents"}),
]

# High enough total losses that financial assistance programs clearly
# matter, even without a parsed coverage limit to compare against.
SIGNIFICANT_LOSS_CAD = 20_000

TOP_K_PER_CATEGORY = 5
URGENT_DAYS = 7
FRESH_HALFLIFE_DAYS = 30
PAST_DUE_GRACE_DAYS = 14

# Tag vocabularies used by personalize_hints to estimate what an upload
# would unlock. Mirrors services.signals.
_INVENTORY_TAGS = {
    "medication_visible", "documents_destroyed", "pet_items_present",
    "smoke_damage", "water_damage", "structural_damage", "total_loss",
    "appliances_lost", "cosmetic_only",
}
_DOCUMENT_TAGS = {"denial_received", "deadline_within_7d", "deadline_within_30d"}


@dataclass
class Recommendation:
    resource: dict
    score: float
    reasons: list[str] = field(default_factory=list)
    rank: int = 0
    days_until_deadline: Optional[int] = None
    status: str = "suggested"
    rec_id: Optional[str] = None  # persisted recommendations row id

    def to_dict(self) -> dict:
        return {
            "id": self.resource["id"],
            "type": self.resource["type"],
            "title": self.resource["title"],
            "body": self.resource["body"],
            "url": self.resource.get("url"),
            "phone": self.resource.get("phone"),
            "score": round(self.score, 4),
            "reasons": self.reasons,
            "rank": self.rank,
            "days_until_deadline": self.days_until_deadline,
            "status": self.status,
            "rec_id": self.rec_id,
            # Machine-extracted from a web page (scraped or search-discovered),
            # rather than hand-curated. The UI shows a "confirm on their site"
            # note for these. Seeded catalog rows have human ids and stay trusted.
            "unverified": str(self.resource["id"]).startswith("scraped-"),
        }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def recommend(
    case: dict,
    items: Iterable[dict],
    resources: list[dict],
    top_k_per_category: int = TOP_K_PER_CATEGORY,
    completed_ids: Optional[set[str]] = None,
    inventory: Optional[InventorySignals] = None,
    documents: Optional[DocumentSignals] = None,
    statuses: Optional[dict[str, str]] = None,
) -> dict[str, list[Recommendation]]:
    """Return content-based recommendations grouped by resource ``type``.

    Parameters
    ----------
    case
        Row from ``recovery_cases``. Reads ``disaster_type``, ``region``,
        ``incident_date``, ``insurance_provider``, ``intake_answers``,
        ``derived_tags``.
    items
        Rows from ``case_items``. Their categories, materials, and damage
        descriptors are folded into the case's content query.
    resources
        Rows from ``resources`` (the shared catalog).
    top_k_per_category
        Max suggestions to keep per resource ``type``.
    completed_ids
        Resource ids the user has already marked done; kept for backwards
        compatibility, merged into ``statuses``.
    inventory
        Signals derived from the image-classification pipeline
        (``signals.inventory_signals_from_items``). Its tags join the
        eligibility filter and the query vector; its total estimated value
        feeds the losses-versus-coverage comparison.
    documents
        Signals derived from the Gemini document analyses
        (``signals.document_signals_from_documents``). Supplies an insurer
        fallback, denial/deadline tags, deadline pressure scoring, and the
        parsed coverage limit.
    statuses
        Persisted ``recommendations.status`` by resource id. ``done`` and
        ``dismissed`` are penalized after normalization so they sort last;
        the status is also carried through to the output for the UI.
    """
    statuses = dict(statuses or {})
    for rid in completed_ids or set():
        statuses.setdefault(rid, "done")
    items = list(items)

    region = case.get("region")
    disaster = case.get("disaster_type")
    tags = set(case.get("derived_tags") or [])
    if inventory is not None:
        tags |= inventory.tags
    if documents is not None:
        tags |= documents.tags
    # The case's own insurer wins; the one Gemini lifted from an uploaded
    # policy/claim PDF fills the gap when the user never typed it in.
    insurer = case.get("insurance_provider") or (
        documents.extracted_insurer if documents else None
    )
    days_since = _days_since(case.get("incident_date"))
    doc_deadlines = list(documents.deadlines) if documents else []
    total_value = float(inventory.total_value) if inventory else 0.0
    coverage_limit = documents.coverage_limit_cad if documents else None

    # 1. eligibility filter (excludes are hard; requires are soft, see
    #    _requires_match)
    candidates: list[tuple[dict, set[str]]] = []
    for r in resources:
        if not (_region_ok(r, region) and _disaster_ok(r, disaster)
                and _window_ok(r, days_since)):
            continue
        keep, unconfirmed = _requires_match(r, tags)
        if not keep:
            continue
        candidates.append((r, unconfirmed))
    if not candidates:
        return {}

    # 2. content (TF-IDF cosine)
    query = _build_query(case, items, tags)
    docs = [_build_document(r) for r, _ in candidates]
    sims = _cosine(query, docs)

    # 3. score + reasons
    recs: list[Recommendation] = []
    for (r, unconfirmed), content_score in zip(candidates, sims):
        reasons: list[str] = []
        score = W_CONTENT * float(content_score)
        if content_score >= 0.15:
            reasons.append("matches your situation")

        # tag overlap depth
        overlap = set(r.get("requires") or []) & tags
        if overlap:
            sample = next(iter(overlap)).replace("_", " ")
            reasons.append(f"you mentioned: {sample}")
            score += W_TAG_OVERLAP * (len(overlap) / max(len(r.get("requires") or []), 1))

        # requires tags we couldn't confirm from what's been shared so far
        if unconfirmed:
            sample = ", ".join(sorted(t.replace("_", " ") for t in list(unconfirmed)[:2]))
            reasons.append(f"worth double-checking that this fits you (it mentions: {sample})")
            score -= PENALTY_UNCONFIRMED * (len(unconfirmed) / max(len(r.get("requires") or []), 1))

        # insurer-specific match
        if insurer and r.get("insurance_companies"):
            if insurer.lower() in [s.lower() for s in r["insurance_companies"]]:
                score += W_INSURER
                reasons.append(f"specific to {insurer}")

        # freshness for scraped entries. The date reflects when we last
        # verified the listing, not when the program itself changed.
        fresh = _freshness(r.get("scraped_at"))
        score += W_FRESHNESS * fresh
        if fresh >= 0.8 and r.get("scraped_at"):
            reasons.append("we verified this listing recently")

        # urgency for immediate-need categories
        if days_since is not None and days_since <= URGENT_DAYS and r["type"] in {"shelter", "health"}:
            score += W_URGENCY
            reasons.append("worth doing soon, since this happened so recently")

        # deadline pressure: the resource's own eligibility window or a
        # deadline Gemini pulled out of an uploaded document. Closer (or
        # just past) means higher.
        deadline_score, days_until = _deadline_pressure(
            r, days_since, doc_deadlines, reasons,
        )
        score += W_DEADLINE * deadline_score

        # losses vs. coverage: the most personal signal we have. Uses the
        # inventory's total estimated value against the largest coverage
        # figure parsed from an uploaded policy.
        score += _value_pressure(r, total_value, coverage_limit, reasons)

        # photo-derived reason copy: cite the image pipeline when the
        # resource matches a damage signal. Static templates, no LLM here.
        if inventory is not None:
            _add_inventory_reasons(r, tags, reasons)
        if documents is not None and documents.denial_flag and r["id"] == "gio-ombud":
            reasons.append("your insurance documents look like a denial, and this is a good place to turn next")
        # A denial makes every legal-escalation resource (lawyer referral,
        # ombudsman, public adjuster) jump the queue.
        if documents is not None and documents.denial_flag and r.get("type") == "legal":
            score += W_URGENCY
            if not any("denial" in reason for reason in reasons):
                reasons.append("because your documents mention a denial, knowing your escalation options matters now")

        if not reasons:
            reasons.append("generally helpful in situations like yours")

        recs.append(Recommendation(
            resource=r, score=score, reasons=reasons,
            days_until_deadline=days_until,
            status=statuses.get(r["id"], "suggested"),
        ))

    # 3b. normalize to [0, 1] within this request so the UI can show
    # meaningful relative labels, then sink done/dismissed below zero.
    max_score = max((rec.score for rec in recs), default=0.0)
    if max_score > 0:
        for rec in recs:
            rec.score = max(rec.score, 0.0) / max_score
    for rec in recs:
        if rec.status == "done":
            rec.score -= PENALTY_DONE
        elif rec.status in ("dismissed", "not_relevant"):
            # "not_relevant" is explicit negative feedback (this does not apply
            # to me), "dismissed" is hide-for-now. Both sink out of the plan; the
            # distinction is kept for the status-change telemetry that will train
            # the ranker.
            rec.score -= PENALTY_DISMISSED

    # 4. group by type, sort, take top-K, set rank
    by_type: dict[str, list[Recommendation]] = {}
    for rec in recs:
        by_type.setdefault(rec.resource["type"], []).append(rec)
    for t in by_type:
        by_type[t].sort(key=lambda x: x.score, reverse=True)
        by_type[t] = by_type[t][:top_k_per_category]
        for i, rec in enumerate(by_type[t]):
            rec.rank = i
    return by_type


# ---------------------------------------------------------------------------
# Personalization hints ("what would sharing more unlock?")
# ---------------------------------------------------------------------------

def personalize_hints(
    case: dict,
    items: list[dict],
    resources: list[dict],
    inventory: Optional[InventorySignals],
    documents: Optional[DocumentSignals],
) -> list[dict]:
    """Suggest the inputs that would most improve the plan, with a count of
    catalog resources each one could unlock or sharpen. Shapes match the
    frontend's PersonalizeHint type."""
    hints: list[dict] = []

    def _titles(rs: list[dict]) -> list[str]:
        return [r.get("title", "") for r in rs[:3] if r.get("title")]

    if not items:
        gated = [r for r in resources if set(r.get("requires") or []) & _INVENTORY_TAGS]
        hints.append({
            "question_id": "add_inventory_photos",
            "estimated_unlock_cad": 0,
            "would_unlock": _titles(gated),
            "copy": (
                "Adding a few room photos lets us spot damage we can match to "
                f"specific programs. Around {len(gated)} resources look for that kind of detail."
                if gated else
                "Adding a few room photos helps us understand your damage and "
                "tailor the plan to what you actually lost."
            ),
        })

    if documents is None:
        insurer_specific = [r for r in resources if r.get("insurance_companies")]
        deadline_aware = [r for r in resources if r.get("type") in _DEADLINE_TYPES]
        hints.append({
            "question_id": "upload_policy",
            "estimated_unlock_cad": 0,
            "would_unlock": _titles(insurer_specific or deadline_aware),
            "copy": (
                "Uploading your insurance policy or claim letters unlocks deadline "
                "tracking and lets us compare your losses against your coverage."
            ),
        })

    insurer = case.get("insurance_provider") or (
        documents.extracted_insurer if documents else None
    )
    if not insurer:
        insurer_specific = [r for r in resources if r.get("insurance_companies")]
        if insurer_specific:
            hints.append({
                "question_id": "name_your_insurer",
                "estimated_unlock_cad": 0,
                "would_unlock": _titles(insurer_specific),
                "copy": (
                    "Telling us who insures you helps surface programs and contacts "
                    f"specific to your company. We know of {len(insurer_specific)} of those."
                ),
            })

    if not case.get("incident_date"):
        windowed = [r for r in resources if r.get("eligibility_days") is not None]
        if windowed:
            hints.append({
                "question_id": "add_incident_date",
                "estimated_unlock_cad": 0,
                "would_unlock": _titles(windowed),
                "copy": (
                    "Adding the date this happened lets us track application windows "
                    "for you, so nothing quietly closes."
                ),
            })

    return hints


# ---------------------------------------------------------------------------
# Query / document construction
# ---------------------------------------------------------------------------

# Lightweight, no-API semantic boost. TF-IDF only matches shared words, so a
# user tagged "displaced" misses a resource that says "evacuees", and a wildfire
# case misses one about "smoke damage". We widen the *query* (never the catalog)
# with domain synonyms before vectorizing, so recall improves without an
# embedding model or any external call. Keys match whole, lowercased query parts.
_SYNONYMS: dict[str, list[str]] = {
    "wildfire": ["fire", "smoke", "ash", "soot"],
    "flood": ["water damage", "flooding", "overland water", "sewer backup"],
    "tornado": ["wind", "windstorm", "storm"],
    "hurricane": ["wind", "windstorm", "storm"],
    "displaced": ["evacuated", "evacuee", "out of home"],
    "needs_shelter": ["shelter", "emergency housing", "nowhere to stay"],
    "renter": ["tenant", "rental", "lease"],
    "owner": ["homeowner", "mortgage"],
    "uninsured": ["no insurance", "not insured"],
    "income_disrupted": ["lost income", "out of work", "unemployed", "wage loss"],
    "on_assistance": ["income support", "social assistance", "benefits"],
    "has_pets": ["pet", "animal"],
    "has_disability": ["disability", "accessibility", "accessible", "medical needs"],
    "has_seniors": ["senior", "elderly", "older adult"],
    "has_kids": ["children", "child", "family"],
    "on_reserve_or_metis": ["indigenous", "first nation", "metis", "band office"],
    "first_nation_reserve": ["indigenous", "first nation", "band office", "reserve"],
    "metis_settlement": ["indigenous", "metis settlement"],
    "inuit_community": ["indigenous", "inuit"],
    "smoke_damage": ["smoke", "soot"],
    "water_damage": ["flood", "water", "mold", "moisture"],
    "structural_damage": ["structural", "building damage", "foundation"],
    "total_loss": ["destroyed", "complete loss"],
}


def _build_query(case: dict, items: list[dict], tags: set[str]) -> str:
    parts: list[str] = []
    if case.get("disaster_type"):
        parts.append(case["disaster_type"])
    if case.get("region"):
        parts.append(case["region"])
    parts.extend(sorted(tags))
    for it in items:
        for k in ("category", "material", "damage_type", "damage_severity"):
            v = it.get(k)
            if v:
                parts.append(str(v))
        if it.get("description"):
            parts.append(str(it["description"]))

    # Widen with domain synonyms so different wording still matches.
    expanded = list(parts)
    for p in parts:
        expanded.extend(_SYNONYMS.get(str(p).strip().lower(), ()))
    return " ".join(expanded) if expanded else "disaster recovery"


def _build_document(r: dict) -> str:
    # Prefer the DB-generated search_text when present (server materialises it).
    text = r.get("search_text")
    if text:
        return text
    return " ".join([
        r.get("title", ""),
        r.get("body", ""),
        r.get("type", ""),
        " ".join(r.get("disaster_types") or []),
        " ".join(r.get("requires") or []),
    ])


# The resource corpus changes rarely (catalog refreshes), so cache the
# fitted vectorizer + matrix per corpus and only transform the query per
# request. Single-slot cache: one catalog per deployment in practice.
_VEC_CACHE: dict[str, tuple] = {}


def _cosine(query: str, docs: list[str]) -> np.ndarray:
    key = str(hash(tuple(docs)))
    cached = _VEC_CACHE.get(key)
    if cached is None:
        vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=1)
        matrix = vec.fit_transform(docs)
        _VEC_CACHE.clear()
        _VEC_CACHE[key] = (vec, matrix)
    else:
        vec, matrix = cached
    q = vec.transform([query])
    return cosine_similarity(q, matrix).flatten()


# ---------------------------------------------------------------------------
# Eligibility helpers
# ---------------------------------------------------------------------------

def _region_ok(r: dict, region: Optional[str]) -> bool:
    """Hierarchical-ish region match: exact, case-insensitive, or one side
    contained in the other ("AB" matches "Calgary, AB"). "*" matches all."""
    rgn = (r.get("region") or "*").strip()
    if rgn == "*" or not region:
        return True
    a, b = rgn.lower(), str(region).strip().lower()
    return a == b or a in b or b in a


def _disaster_ok(r: dict, disaster: Optional[str]) -> bool:
    types = r.get("disaster_types") or ["*"]
    if "*" in types or not disaster:
        return True
    return disaster in types


def _requires_match(r: dict, tags: set[str]) -> tuple[bool, set[str]]:
    """Soft requires / hard excludes.

    Returns (keep, unconfirmed_tags). Tags we don't have are unknown, not
    disqualifying: the user may simply not have uploaded the photo or
    document that would prove them. Keep the resource when requirements are
    fully met, partially met, or when we know nothing about the user yet;
    drop it only when we do have tags and none of them overlap (everything
    we know points away from this resource). Excluded tags always drop."""
    requires = set(r.get("requires") or [])
    excludes = set(r.get("excludes") or [])
    if excludes & tags:
        return False, set()
    if not requires:
        return True, set()
    missing = requires - tags
    if not missing:
        return True, set()
    if tags and not (requires & tags):
        return False, set()
    return True, missing


def _window_ok(r: dict, days_since: Optional[int]) -> bool:
    window = r.get("eligibility_days")
    if window is None or days_since is None:
        return True
    return days_since <= window


# ---------------------------------------------------------------------------
# Signal-derived scoring helpers
# ---------------------------------------------------------------------------

def _relevant_deadlines(r: dict, deadlines: list[DocumentDeadline]) -> list[DocumentDeadline]:
    """Route document deadlines to the resource types they belong to. A
    claim deadline should pressure insurance resources, a DRP application
    date the financial ones. Deadlines that match no route fall back to all
    deadline-aware types."""
    if r["type"] not in _DEADLINE_TYPES:
        return []
    relevant: list[DocumentDeadline] = []
    for d in deadlines:
        text = f"{d.label} {d.source_doc}"
        routed_types: set[str] = set()
        for pattern, types in _DEADLINE_ROUTES:
            if pattern.search(text):
                routed_types |= types
        if not routed_types:
            routed_types = set(_DEADLINE_TYPES)
        if r["type"] in routed_types:
            relevant.append(d)
    return relevant


def _deadline_pressure(
    r: dict,
    days_since: Optional[int],
    doc_deadlines: list[DocumentDeadline],
    reasons: list[str],
) -> tuple[float, Optional[int]]:
    """Two deadline sources: the resource's own ``eligibility_days`` window,
    and deadlines extracted from uploaded documents, routed by relevance.
    Recently missed deadlines still surface, since asking for an extension
    is often possible. Returns (score in [0, 1], days_until_deadline,
    negative when just past)."""
    candidates: list[tuple[int, str]] = []  # (days_left, reason copy)

    window = r.get("eligibility_days")
    if window is not None and days_since is not None:
        days_left = int(window) - days_since
        if days_left >= 0:
            candidates.append((
                days_left,
                f"the application window closes in {days_left} day{'s' if days_left != 1 else ''}",
            ))

    today = date.today()
    for d in _relevant_deadlines(r, doc_deadlines):
        days_left = (d.due_date - today).days
        if days_left >= 0:
            candidates.append((
                days_left,
                f"your {d.source_doc} mentions a deadline, "
                f"{days_left} day{'s' if days_left != 1 else ''} left",
            ))
        elif days_left >= -PAST_DUE_GRACE_DAYS:
            ago = -days_left
            candidates.append((
                days_left,
                f"a deadline in your {d.source_doc} passed {ago} day{'s' if ago != 1 else ''} ago. "
                "It is still worth calling to ask about an extension",
            ))

    if not candidates:
        return 0.0, None

    days_left, label = min(candidates, key=lambda c: c[0])
    # 1.0 at (or just past) 0 days, decaying to 0 by 60 days out.
    score = max(0.0, 1.0 - max(days_left, 0) / 60.0)
    # Only shout about genuinely close deadlines.
    if days_left <= 30:
        reasons.append(label)
    return score, days_left


def _value_pressure(
    r: dict,
    total_value: float,
    coverage_limit: Optional[float],
    reasons: list[str],
) -> float:
    """Boost financial and insurance resources when the inventory's total
    estimated value is significant, and especially when it looks like it
    may exceed the coverage parsed from an uploaded policy."""
    if total_value <= 0:
        return 0.0
    if (
        coverage_limit
        and total_value > coverage_limit
        and r["type"] in {"insurance", "financial", "legal"}
    ):
        reasons.append(
            f"your listed losses (about ${total_value:,.0f}) may be more than the "
            f"coverage we saw in your policy (about ${coverage_limit:,.0f}), so "
            "extra support could really help"
        )
        return W_VALUE
    if total_value >= SIGNIFICANT_LOSS_CAD and r["type"] == "financial":
        reasons.append(
            "your losses add up to a significant amount, and financial support "
            "programs are built for exactly that"
        )
        return W_VALUE * 0.5
    return 0.0


def _add_inventory_reasons(r: dict, tags: set[str], reasons: list[str]) -> None:
    if "structural_damage" in tags and r["id"] in {"ab-drp", "habitat-ab", "samaritans-purse"}:
        reasons.append("your damage photos suggest structural loss, and this program covers that")
    elif "total_loss" in tags and r["id"] in {"ab-drp", "habitat-ab"}:
        reasons.append("your photos suggest a total loss, so major rebuild programs apply")
    if "medication_visible" in tags and r["type"] == "health":
        reasons.append("your photos showed medication left behind, and Health Link can help with refills")
    if "documents_destroyed" in tags and r["type"] == "documents":
        reasons.append("your photos suggest documents were lost. Replacement fees are waived after a declared disaster")
    if "pet_items_present" in tags and r["id"] in {"red-cross-lodging", "211-alberta", "pet-friendly-shelters", "ab-spca-disaster"}:
        reasons.append("your photos showed pet items, and they can help locate pet friendly lodging")


# ---------------------------------------------------------------------------
# Numeric helpers
# ---------------------------------------------------------------------------

def _freshness(scraped_at) -> float:
    if not scraped_at:
        return 0.5
    try:
        d = date.fromisoformat(str(scraped_at)[:10])
    except ValueError:
        return 0.5
    age = max((date.today() - d).days, 0)
    return float(0.5 ** (age / FRESH_HALFLIFE_DAYS))


def _days_since(disaster_date) -> Optional[int]:
    if disaster_date is None:
        return None
    if isinstance(disaster_date, datetime):
        d = disaster_date.date()
    elif isinstance(disaster_date, date):
        d = disaster_date
    else:
        try:
            d = date.fromisoformat(str(disaster_date)[:10])
        except ValueError:
            return None
    return max((date.today() - d).days, 0)
