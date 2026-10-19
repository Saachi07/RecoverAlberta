"""ML endpoints: Gemini-backed photo to inventory extraction."""

from __future__ import annotations

from flask import Blueprint, current_app, g, jsonify, request

from ..auth import require_auth
from ..services.gemini_inventory import ModelOverloaded, analyze_room_photo

try:
    from ..services.rate_limit import check_rate_limit
except ImportError:  # pragma: no cover - transitional until rate_limit ships
    def check_rate_limit(user_id: str, key: str, max_per_minute: int) -> bool:
        return True

bp = Blueprint("ml", __name__, url_prefix="/ml")


# Largest demo upload we'll accept. Demo scans are unauthenticated, so we keep
# the door narrow: one reasonably sized room photo, nothing more.
DEMO_MAX_BYTES = 12 * 1024 * 1024


@bp.post("/demo-analyze-photo")
def demo_analyze_photo():
    """Public, no-login scan for the landing page "Try it yourself" zone.

    Same Gemini scan as the authed endpoint, but unauthenticated so a visitor
    can see the product before signing up. The image is only ever passed to the
    model in-memory and is never written to storage, so it is gone the moment
    this request returns.
    """
    if "image" not in request.files:
        return jsonify({"error": "image file is required"}), 400
    f = request.files["image"]
    if not f or not f.filename:
        return jsonify({"error": "image file is required"}), 400

    blob = f.read()
    if not blob:
        return jsonify({"error": "empty image"}), 400
    if len(blob) > DEMO_MAX_BYTES:
        return jsonify({"error": "That photo is a little large for the demo. Try one under 12 MB."}), 413

    api_key = current_app.config.get("GEMINI_API_KEY")
    if not api_key:
        return jsonify({"error": "GEMINI_API_KEY not configured on server"}), 503

    try:
        result = analyze_room_photo(blob, api_key, pre_post="post")
    except ModelOverloaded as exc:
        return jsonify({"error": str(exc)}), 503
    except Exception as exc:  # noqa: BLE001 - surface error to client
        return jsonify({"error": str(exc)}), 500
    return jsonify(result.model_dump())


@bp.post("/analyze-photo")
@require_auth
def analyze_photo():
    # Each scan is a Gemini call; a runaway client could burn the quota for
    # everyone. Ten per minute is far above any real user's pace.
    if not check_rate_limit(g.user_id, "ml.analyze_photo", 10):
        return jsonify({
            "error": "You're scanning photos faster than we can keep up. Please wait a minute and try again."
        }), 429

    if "image" not in request.files:
        return jsonify({"error": "image file is required"}), 400
    f = request.files["image"]
    if not f or not f.filename:
        return jsonify({"error": "image file is required"}), 400

    blob = f.read()
    if not blob:
        return jsonify({"error": "empty image"}), 400

    # "pre"  = before the disaster (proof of what the user owned).
    # "post" = after the disaster (showing the damage).
    # "auto" = let Gemini decide and report it back as detected_phase.
    pre_post = (request.form.get("pre_post") or "post").lower()
    if pre_post not in {"pre", "post", "auto"}:
        pre_post = "post"

    api_key = current_app.config.get("GEMINI_API_KEY")
    if not api_key:
        return jsonify({"error": "GEMINI_API_KEY not configured on server"}), 503

    try:
        result = analyze_room_photo(blob, api_key, pre_post=pre_post)
    except ModelOverloaded as exc:
        # Gemini is temporarily unavailable after retries, tell the client to
        # retry rather than reporting a server bug.
        return jsonify({"error": str(exc)}), 503
    except Exception as exc:  # noqa: BLE001 - surface error to client
        return jsonify({"error": str(exc)}), 500
    return jsonify(result.model_dump())
