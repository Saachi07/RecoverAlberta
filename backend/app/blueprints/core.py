"""Health probe, verifies the app is up and that Supabase is reachable."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify

from ..extensions import anon_client

bp = Blueprint("health", __name__)


@bp.get("/health")
def health():
    payload: dict = {"status": "ok", "supabase": "unconfigured"}
    if current_app.config.get("SUPABASE_URL") and current_app.config.get("SUPABASE_ANON_KEY"):
        try:
            anon_client().table("resources").select("id").limit(1).execute()
            payload["supabase"] = "ok"
        except Exception as exc:
            payload["supabase"] = "error"
            payload["supabase_error"] = exc.__class__.__name__
            payload["supabase_message"] = str(exc)
            payload["status"] = "degraded"
    status_code = 200 if payload["status"] == "ok" else 503
    return jsonify(payload), status_code


"""Small public metadata endpoints.

Lookup data the frontend needs but should not hardcode, so the client and
server cannot drift apart. No auth: nothing here is user-specific.
"""

from __future__ import annotations

from flask import Blueprint, jsonify

bp = Blueprint("meta", __name__, url_prefix="/meta")

# What kind of damage each disaster type usually causes. Used to default
# the damage type on scanned inventory items. Previously hardcoded in
# frontend/src/pages/Inventory.tsx; this is now the single source of truth.
DISASTER_TO_DAMAGE: dict[str, str] = {
    "wildfire": "fire",
    "flood": "water",
    "hurricane": "wind",
    "tornado": "wind",
    "earthquake": "other",
    "other": "other",
}


@bp.get("/damage-mapping")
def damage_mapping():
    return jsonify({"mapping": DISASTER_TO_DAMAGE})


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


CURRENT_TERMS_VERSION = "2026-06-08"
PRIVACY_URL = "/legal/privacy"
TERMS_URL = "/legal/terms"
ENCRYPTION_NOTICE = (
    "Your data is encrypted in transit (TLS 1.2+) and at rest (AES-256). "
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
