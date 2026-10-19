"""Bridge the Gemini pipelines into recommender signals.

Two upstream pipelines feed the recommender:

* **Image classification** (``gemini_inventory.analyze_room_photo``), its
  items land in ``case_items`` via the Inventory page. From those rows we
  derive an overall damage severity plus semantic tags (smoke_damage,
  appliances_lost, medication_visible, ...).
* **NLP document analysis** (``gemini_documents.analyze_document``), its
  output is persisted as ``user_documents.gemini_analysis``. From those we
  lift the insurer name, hard deadlines, and denial signals.

Both derivations are pure functions over already-persisted rows so the
recommendations endpoint stays read-only and cheap, no Gemini call in the
request path.

The tag vocabulary deliberately matches ``questions/recommender.py`` and the
``requires`` / ``excludes`` arrays in the seeded ``resources`` table.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Iterable, Optional

# Worst-first ordering for case_items.damage_severity values.
_SEVERITY_ORDER = ("destroyed", "severe", "moderate", "minor")

# Keyword → tag rules over an item's name / category / damage_type text.
_ITEM_TAG_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"medication|medicine|prescription|insulin|inhaler|pill", re.I), "medication_visible"),
    (re.compile(r"passport|licen[cs]e|birth certificate|health card|\bid card\b", re.I), "documents_destroyed"),
    (re.compile(r"\bpet\b|leash|kennel|litter|aquarium|bird ?cage|dog|cat", re.I), "pet_items_present"),
    (re.compile(r"smoke|soot|char|burn", re.I), "smoke_damage"),
    (re.compile(r"water|flood|mold|mould", re.I), "water_damage"),
]

_INSURER_FIELD_LABELS = re.compile(r"insurer|insurance (company|provider)|carrier|underwriter", re.I)
_DEADLINE_FIELD_LABELS = re.compile(r"deadline|due|respond by|submit by|file by|expir", re.I)
_DENIAL_WORDS = re.compile(r"\bdeni(?:ed|al)\b|\bdeclined?\b|\brejected\b", re.I)

# Date formats Gemini tends to emit in key_fields values.
_ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_SLASH_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
_MONTH_DATE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b",
    re.I,
)
_MONTHS = {m: i + 1 for i, m in enumerate(
    ("january", "february", "march", "april", "may", "june",
     "july", "august", "september", "october", "november", "december")
)}

# Dollar amounts inside coverage-limit strings ("Contents: $40,000 CAD").
_MONEY = re.compile(r"\$\s?([\d][\d,]*(?:\.\d{1,2})?)")

# A deadline that recently closed is still worth surfacing ("call and ask
# about an extension") rather than silently hiding.
PAST_DUE_GRACE_DAYS = 14


@dataclass
class InventorySignals:
    """What the photo pipeline tells us about the loss."""
    total_value: float = 0.0
    damage_severity: Optional[str] = None  # worst across items
    tags: set[str] = field(default_factory=set)


@dataclass
class DocumentDeadline:
    source_doc: str
    label: str
    due_date: date


@dataclass
class DocumentSignals:
    """What the document pipeline lifted from uploaded PDFs."""
    extracted_insurer: Optional[str] = None
    deadlines: list[DocumentDeadline] = field(default_factory=list)
    denial_flag: bool = False
    tags: set[str] = field(default_factory=set)
    # Largest dollar figure found in coverage_limits strings; compared
    # against the inventory's total estimated value by the recommender.
    coverage_limit_cad: Optional[float] = None


# ---------------------------------------------------------------------------
# Image classification → signals
# ---------------------------------------------------------------------------

def inventory_signals_from_items(items: Iterable[dict]) -> Optional[InventorySignals]:
    """Fold ``case_items`` rows (created from analyzed photos or by hand)
    into one inventory signal. Returns None when there are no items."""
    items = [it for it in items if it]
    if not items:
        return None

    sig = InventorySignals()
    worst_rank = len(_SEVERITY_ORDER)
    for it in items:
        try:
            sig.total_value += float(it.get("estimated_value") or 0.0)
        except (TypeError, ValueError):
            pass

        sev = (it.get("damage_severity") or "").lower()
        if sev in _SEVERITY_ORDER:
            worst_rank = min(worst_rank, _SEVERITY_ORDER.index(sev))

        text = " ".join(
            str(it.get(k) or "")
            for k in ("name", "category", "damage_type", "description")
        )
        damaged = sev in ("moderate", "severe", "destroyed")
        for pattern, tag in _ITEM_TAG_RULES:
            if pattern.search(text):
                # Loss-type tags only make sense for damaged items;
                # damage-type tags (smoke/water) imply damage already.
                if tag in ("documents_destroyed",) and not damaged:
                    continue
                sig.tags.add(tag)
        if damaged and (it.get("category") or "").lower() == "appliance":
            sig.tags.add("appliances_lost")

    if worst_rank < len(_SEVERITY_ORDER):
        sig.damage_severity = _SEVERITY_ORDER[worst_rank]
        if sig.damage_severity == "destroyed":
            sig.tags |= {"total_loss", "structural_damage"}
        elif sig.damage_severity == "severe":
            sig.tags.add("structural_damage")
        elif sig.damage_severity == "minor":
            sig.tags.add("cosmetic_only")
        # moderate deliberately leaves no severity tag, resources gated on
        # either cosmetic or structural shouldn't misfire.
    return sig


# ---------------------------------------------------------------------------
# Document analysis → signals
# ---------------------------------------------------------------------------

def parse_date_loose(value: str) -> Optional[date]:
    """Pull the first recognizable calendar date out of free text."""
    if not value:
        return None
    m = _ISO_DATE.search(value)
    if m:
        y, mo, d = (int(g) for g in m.groups())
        return _safe_date(y, mo, d)
    m = _MONTH_DATE.search(value)
    if m:
        return _safe_date(int(m.group(3)), _MONTHS[m.group(1).lower()], int(m.group(2)))
    m = _SLASH_DATE.search(value)
    if m:
        # Assume m/d/yyyy, the dominant format in our test PDFs.
        return _safe_date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
    return None


def _safe_date(y: int, mo: int, d: int) -> Optional[date]:
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def document_signals_from_documents(
    documents: Iterable[dict],
    today: Optional[date] = None,
) -> Optional[DocumentSignals]:
    """Fold analyzed ``user_documents`` rows into one document signal.

    Each row needs ``name`` and ``gemini_analysis`` (the persisted
    ``DocumentAnalysis``). Rows that were never analyzed are skipped.
    Returns None when nothing was analyzed."""
    analyzed = [d for d in documents if d and d.get("gemini_analysis")]
    if not analyzed:
        return None

    sig = DocumentSignals()
    ref = today or date.today()
    earliest_kept = ref - timedelta(days=PAST_DUE_GRACE_DAYS)
    for row in analyzed:
        analysis = row["gemini_analysis"]
        doc_name = row.get("name") or "document"
        summary_text = " ".join(
            str(analysis.get(k) or "") for k in ("title", "summary")
        )
        if _DENIAL_WORDS.search(summary_text):
            sig.denial_flag = True

        for kf in analysis.get("key_fields") or []:
            label = str(kf.get("label") or "")
            value = str(kf.get("value") or "")
            if not sig.extracted_insurer and _INSURER_FIELD_LABELS.search(label):
                sig.extracted_insurer = value.strip() or None
            if _DEADLINE_FIELD_LABELS.search(label):
                due = parse_date_loose(value)
                if due and due >= earliest_kept:
                    sig.deadlines.append(
                        DocumentDeadline(source_doc=doc_name, label=label, due_date=due)
                    )

        # Rich pipeline output (document_pipeline.analyze_document_rich) merged
        # under "analysis": structured deadlines + flagged issues. Relative
        # durations ("within 30 days") can't be anchored to a calendar date
        # here, so only explicit dates feed the radar.
        rich = analysis.get("analysis") or {}
        for dl in rich.get("deadlines") or []:
            task = str(dl.get("task") or "").strip()
            due = parse_date_loose(str(dl.get("date") or ""))
            if due and due >= earliest_kept:
                sig.deadlines.append(
                    DocumentDeadline(
                        source_doc=doc_name,
                        label=task or "deadline",
                        due_date=due,
                    )
                )
        for limit in rich.get("coverage_limits") or []:
            for m in _MONEY.finditer(str(limit)):
                try:
                    amount = float(m.group(1).replace(",", ""))
                except ValueError:
                    continue
                if sig.coverage_limit_cad is None or amount > sig.coverage_limit_cad:
                    sig.coverage_limit_cad = amount
        rich_text = " ".join(
            [str(rich.get("plain_language_summary") or "")]
            + [str(f.get("message") or "") for f in rich.get("flagged_issues") or []]
        )
        if _DENIAL_WORDS.search(rich_text):
            sig.denial_flag = True

    if sig.denial_flag:
        sig.tags.add("denial_received")
    if sig.deadlines:
        days_left = (min(d.due_date for d in sig.deadlines) - ref).days
        if days_left <= 7:
            sig.tags.add("deadline_within_7d")
        elif days_left <= 30:
            sig.tags.add("deadline_within_30d")
    return sig
