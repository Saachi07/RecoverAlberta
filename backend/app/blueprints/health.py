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
