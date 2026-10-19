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
