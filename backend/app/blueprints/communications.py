"""Claim communications log endpoints.

A dated record of every call, email, and meeting about a claim. This
feature exists because a real survivor's insurer changed its story about
what her personal property coverage included, and she had nothing in
writing to push back with. The log gives users that paper trail: who they
spoke to, when, and what was said.

The 'discrepancy' kind pairs insurer_statement (what the insurer said)
with summary (what the policy or the user says happened), so conflicts
are captured side by side while memories are fresh.
"""

from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, g, jsonify, request

from ..auth import require_auth
from ..extensions import user_client

bp = Blueprint("communications", __name__)

WRITABLE = {
    "occurred_at",
    "contact_name",
    "organization",
    "channel",
    "kind",
    "summary",
    "insurer_statement",
    "follow_up",
}

CHANNELS = {"phone", "email", "in_person", "mail", "other"}
KINDS = {"note", "call", "email", "meeting", "discrepancy"}


def _validated(data: dict) -> tuple[dict | None, str | None]:
    """Filter to writable fields and validate enums. Returns (row, error)."""
    row = {k: v for k, v in data.items() if k in WRITABLE}
    if row.get("channel") and row["channel"] not in CHANNELS:
        return None, "channel must be one of: " + ", ".join(sorted(CHANNELS))
    if row.get("kind") and row["kind"] not in KINDS:
        return None, "kind must be one of: " + ", ".join(sorted(KINDS))
    return row, None


@bp.get("/cases/<case_id>/communications")
@require_auth
def list_communications(case_id: str):
    sb = user_client(g.access_token)
    res = (
        sb.table("case_communications")
        .select("*")
        .eq("case_id", case_id)
        .eq("user_id", g.user_id)
        .is_("deleted_at", "null")
        .order("occurred_at", desc=True)
        .execute()
    )
    return jsonify({"communications": res.data or []})


@bp.post("/cases/<case_id>/communications")
@require_auth
def create_communication(case_id: str):
    data = request.get_json(silent=True) or {}
    if not (data.get("summary") or "").strip():
        return jsonify({"error": "Please write a short summary of what was said."}), 400
    row, err = _validated(data)
    if err:
        return jsonify({"error": err}), 400
    row["case_id"] = case_id
    row["user_id"] = g.user_id
    sb = user_client(g.access_token)
    res = sb.table("case_communications").insert(row).execute()
    created = res.data[0] if res.data else None
    return jsonify({"communication": created}), 201


@bp.patch("/communications/<comm_id>")
@require_auth
def update_communication(comm_id: str):
    data = request.get_json(silent=True) or {}
    row, err = _validated(data)
    if err:
        return jsonify({"error": err}), 400
    if not row:
        return jsonify({"error": "no updatable fields provided"}), 400
    if "summary" in row and not (row["summary"] or "").strip():
        return jsonify({"error": "The summary cannot be empty."}), 400
    sb = user_client(g.access_token)
    res = (
        sb.table("case_communications")
        .update(row)
        .eq("id", comm_id)
        .eq("user_id", g.user_id)
        .execute()
    )
    if not res.data:
        return jsonify({"error": "not found"}), 404
    return jsonify({"communication": res.data[0]})


@bp.delete("/communications/<comm_id>")
@require_auth
def delete_communication(comm_id: str):
    # Soft delete: the log is evidence, so nothing is destroyed outright.
    sb = user_client(g.access_token)
    res = (
        sb.table("case_communications")
        .update({"deleted_at": datetime.now(timezone.utc).isoformat()})
        .eq("id", comm_id)
        .eq("user_id", g.user_id)
        .execute()
    )
    if not res.data:
        return jsonify({"error": "not found"}), 404
    return jsonify({"ok": True})
