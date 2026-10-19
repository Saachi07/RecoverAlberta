"""Additional living expenses (ALE) tracker endpoints.

While a home is uninhabitable, most policies reimburse extra costs of
living elsewhere: hotels, meals above normal grocery spend, transport,
storage, pet boarding. Insurers reimburse fastest when receipts are
organized and itemized, so the tracker keeps a dated, categorized list
with a running total the user can hand to their adjuster.
"""

from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, g, jsonify, request

from ..auth import require_auth
from ..extensions import user_client

bp = Blueprint("ale", __name__)

WRITABLE = {"category", "vendor", "amount", "expense_date", "receipt_url", "notes"}

# "cleanup" covers hiring someone to safely clear or retrieve belongings from
# an uninhabitable unit, a real, often large displaced-living cost survivors
# told us was missing from the usual categories.
CATEGORIES = {"hotel", "meals", "transport", "storage", "pets", "cleanup", "other"}


def sum_expenses(rows: list[dict]) -> float:
    """Total of expense amounts. Pure helper so the math is testable."""
    total = 0.0
    for row in rows:
        try:
            total += float(row.get("amount") or 0)
        except (TypeError, ValueError):
            continue
    return round(total, 2)


def _validate_amount(value) -> float | None:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return None
    if amount <= 0:
        return None
    return amount


@bp.get("/cases/<case_id>/ale-expenses")
@require_auth
def list_expenses(case_id: str):
    sb = user_client(g.access_token)
    res = (
        sb.table("ale_expenses")
        .select("*")
        .eq("case_id", case_id)
        .eq("user_id", g.user_id)
        .is_("deleted_at", "null")
        .order("expense_date", desc=True)
        .execute()
    )
    rows = res.data or []
    return jsonify({"expenses": rows, "total": sum_expenses(rows)})


@bp.post("/cases/<case_id>/ale-expenses")
@require_auth
def create_expense(case_id: str):
    data = request.get_json(silent=True) or {}
    category = data.get("category")
    if category not in CATEGORIES:
        return jsonify({"error": "category must be one of: " + ", ".join(sorted(CATEGORIES))}), 400
    amount = _validate_amount(data.get("amount"))
    if amount is None:
        return jsonify({"error": "Please enter the amount you paid (a positive number)."}), 400

    row = {k: v for k, v in data.items() if k in WRITABLE}
    row["amount"] = amount
    row["case_id"] = case_id
    row["user_id"] = g.user_id
    sb = user_client(g.access_token)
    res = sb.table("ale_expenses").insert(row).execute()
    created = res.data[0] if res.data else None
    return jsonify({"expense": created}), 201


@bp.patch("/ale-expenses/<expense_id>")
@require_auth
def update_expense(expense_id: str):
    data = request.get_json(silent=True) or {}
    row = {k: v for k, v in data.items() if k in WRITABLE}
    if not row:
        return jsonify({"error": "no updatable fields provided"}), 400
    if "category" in row and row["category"] not in CATEGORIES:
        return jsonify({"error": "category must be one of: " + ", ".join(sorted(CATEGORIES))}), 400
    if "amount" in row:
        amount = _validate_amount(row["amount"])
        if amount is None:
            return jsonify({"error": "Please enter the amount you paid (a positive number)."}), 400
        row["amount"] = amount
    sb = user_client(g.access_token)
    res = (
        sb.table("ale_expenses")
        .update(row)
        .eq("id", expense_id)
        .eq("user_id", g.user_id)
        .execute()
    )
    if not res.data:
        return jsonify({"error": "not found"}), 404
    return jsonify({"expense": res.data[0]})


@bp.delete("/ale-expenses/<expense_id>")
@require_auth
def delete_expense(expense_id: str):
    sb = user_client(g.access_token)
    res = (
        sb.table("ale_expenses")
        .update({"deleted_at": datetime.now(timezone.utc).isoformat()})
        .eq("id", expense_id)
        .eq("user_id", g.user_id)
        .execute()
    )
    if not res.data:
        return jsonify({"error": "not found"}), 404
    return jsonify({"ok": True})
