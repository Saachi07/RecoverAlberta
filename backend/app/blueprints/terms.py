"""Terms of service + privacy policy acceptance tracking.

A static current version lives in CURRENT_TERMS_VERSION. The frontend
calls GET /terms to learn the active version + URLs, and POST /terms/accept
once the user clicks through. profiles.terms_accepted_at / terms_version
hold the audit trail; bump CURRENT_TERMS_VERSION to force a re-prompt.

We also tell the user, in the GET response, that their data is encrypted
in transit (HTTPS) and at rest (Supabase managed Postgres + Storage use
AES-256). The frontend surfaces that copy verbatim.
"""

from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, g, jsonify, request

from ..auth import require_auth
from ..extensions import user_client

bp = Blueprint("terms", __name__, url_prefix="/terms")


CURRENT_TERMS_VERSION = "2026-10-18"
PRIVACY_URL = "/legal/privacy"
TERMS_URL = "/legal/terms"
ENCRYPTION_NOTICE = (
    "Your data is encrypted in transit and at rest by our infrastructure providers. "
    "Documents are stored in a private bucket and only accessible via "
    "short-lived signed links issued to your authenticated session."
)


@bp.get("")
def get_terms():
    """Public, the frontend hits this before showing the consent screen."""
    return jsonify({
        "current_version": CURRENT_TERMS_VERSION,
        "privacy_url": PRIVACY_URL,
        "terms_url": TERMS_URL,
        "encryption_notice": ENCRYPTION_NOTICE,
    })


@bp.get("/status")
@require_auth
def acceptance_status():
    sb = user_client(g.access_token)
    res = (
        sb.table("profiles")
        .select("terms_accepted_at, terms_version")
        .eq("id", g.user_id)
        .maybe_single()
        .execute()
    )
    data = res.data or {}
    accepted = data.get("terms_version") == CURRENT_TERMS_VERSION
    return jsonify({
        "accepted": accepted,
        "current_version": CURRENT_TERMS_VERSION,
        "accepted_version": data.get("terms_version"),
        "accepted_at": data.get("terms_accepted_at"),
    })


@bp.post("/accept")
@require_auth
def accept_terms():
    body = request.get_json(silent=True) or {}
    # Lock acceptance to the server's current version. Clients can pass
    # `version` to confirm they saw the same one (mostly a sanity check
    #, we still store our own).
    if body.get("version") and body["version"] != CURRENT_TERMS_VERSION:
        return jsonify({
            "error": "stale terms version",
            "current_version": CURRENT_TERMS_VERSION,
        }), 409

    now = datetime.now(timezone.utc).isoformat()
    sb = user_client(g.access_token)
    res = (
        sb.table("profiles")
        .update({
            "terms_accepted_at": now,
            "terms_version": CURRENT_TERMS_VERSION,
        })
        .eq("id", g.user_id)
        .execute()
    )
    return jsonify({
        "accepted": True,
        "version": CURRENT_TERMS_VERSION,
        "accepted_at": now,
        "profile": res.data[0] if res.data else None,
    })
