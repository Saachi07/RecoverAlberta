from __future__ import annotations

from flask import Blueprint, jsonify

from ..auth import require_auth
from ..services.weather_alerts import fetch_alerts

bp = Blueprint("alerts", __name__, url_prefix="/alerts")


@bp.get("")
@require_auth
def list_alerts():
    """Return normalized Alberta 511 alerts.

    This endpoint is intentionally simple: it proxies and normalizes the
    upstream feed. We only return alerts; client-side can decide which
    to surface as notifications.
    """
    alerts = fetch_alerts()
    return jsonify({"alerts": alerts})
