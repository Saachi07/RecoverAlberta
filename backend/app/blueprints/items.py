"""Case-item CRUD, damaged objects in a user's library.

Originally items belonged to a single case (case_items.case_id NOT NULL).
After migration 0006 they're a per-user library that can optionally be
linked to a case, see the SQL for the new RLS policies.

Routes:
    /items                         user-scoped CRUD (the library)
    /cases/<case_id>/items         legacy + scoped view for the recommender

These rows feed the content-based filter: an item's ``category``,
``material``, ``damage_type`` and ``damage_severity`` are appended to the
query vector the recommender builds for that case.
"""

from __future__ import annotations

import uuid

from flask import Blueprint, g, jsonify, request

from ..auth import require_auth
from ..extensions import service_client, user_client
from ..pagination import parse_pagination
from ..services.item_fields import WRITABLE, clean_item_row  # noqa: F401 (WRITABLE re-exported)

bp = Blueprint("items", __name__)

# Public-read storage bucket for item photos (see migration 0007). Writes go
# through the service role; reads are plain public URLs the browser loads.
IMAGE_BUCKET = "item-images"
IMAGE_EXT = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/heic": ".heic",
}

# Per-case view (kept for the recommender and the case-scoped Inventory page)
case_bp = Blueprint("case_items", __name__, url_prefix="/cases/<case_id>/items")

# User library
lib_bp = Blueprint("user_items", __name__, url_prefix="/items")

# WRITABLE and the validation for the evidence fields (migration 0012) live in
# services/item_fields.py so the rules can be unit-tested without Flask.


def _insert_item(sb, row):
    """Insert a case_items row, turning a DB error into a clean 4xx/5xx
    instead of an opaque 500. The common cause of a failed insert here is a
    column missing on the deployed DB (run the migrations) or an RLS denial.
    """
    try:
        res = sb.table("case_items").insert(row).execute()
    except Exception as exc:  # noqa: BLE001, surface the real cause to the client
        return None, (jsonify({"error": f"could not save item: {exc}"}), 500)
    if not res.data:
        return None, (jsonify({"error": "item was not saved"}), 500)
    return res.data[0], None


# ---------------------------------------------------------------------------
# Case-scoped (legacy + recommender)
# ---------------------------------------------------------------------------
@case_bp.get("")
@require_auth
def list_items_for_case(case_id: str):
    sb = user_client(g.access_token)
    res = (
        sb.table("case_items")
        .select("*")
        .eq("case_id", case_id)
        .order("created_at", desc=False)
        .execute()
    )
    return jsonify({"items": res.data or []})


@case_bp.post("")
@require_auth
def create_item_for_case(case_id: str):
    data = request.get_json(silent=True) or {}
    if not data.get("name"):
        return jsonify({"error": "name is required"}), 400
    row, problem = clean_item_row(data)
    if problem:
        return jsonify({"error": problem}), 400
    row["case_id"] = case_id
    row["user_id"] = g.user_id
    sb = user_client(g.access_token)
    item, error = _insert_item(sb, row)
    if error:
        return error
    return jsonify({"item": item}), 201


@case_bp.post("/bulk")
@require_auth
def create_items_bulk(case_id: str):
    """Insert many items for a case in one round-trip.

    The photo-scan flow drafts a whole room at once; saving them one POST at a
    time was slow and non-atomic (a failure midway left a partial save). This
    inserts the batch in a single call.
    """
    data = request.get_json(silent=True) or {}
    items = data.get("items")
    if not isinstance(items, list) or not items:
        return jsonify({"error": "items array is required"}), 400

    rows = []
    for it in items:
        if not isinstance(it, dict) or not it.get("name"):
            return jsonify({"error": "each item needs a name"}), 400
        row, problem = clean_item_row(it)
        if problem:
            return jsonify({"error": f"item {len(rows) + 1}: {problem}"}), 400
        row["case_id"] = case_id
        row["user_id"] = g.user_id
        rows.append(row)

    sb = user_client(g.access_token)
    try:
        res = sb.table("case_items").insert(rows).execute()
    except Exception as exc:  # noqa: BLE001, surface the real cause
        return jsonify({"error": f"could not save items: {exc}"}), 500
    return jsonify({"items": res.data or []}), 201


@case_bp.patch("/<item_id>")
@require_auth
def update_item_for_case(case_id: str, item_id: str):
    data = request.get_json(silent=True) or {}
    row, problem = clean_item_row(data)
    if problem:
        return jsonify({"error": problem}), 400
    if not row:
        return jsonify({"error": "no updatable fields provided"}), 400
    sb = user_client(g.access_token)
    res = (
        sb.table("case_items")
        .update(row)
        .eq("id", item_id)
        .eq("case_id", case_id)
        .execute()
    )
    if not res.data:
        return jsonify({"error": "not found"}), 404
    return jsonify({"item": res.data[0]})


@case_bp.delete("/<item_id>")
@require_auth
def delete_item_for_case(case_id: str, item_id: str):
    sb = user_client(g.access_token)
    res = (
        sb.table("case_items")
        .delete()
        .eq("id", item_id)
        .eq("case_id", case_id)
        .execute()
    )
    if not res.data:
        return jsonify({"error": "not found"}), 404
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# User library
# ---------------------------------------------------------------------------
@lib_bp.get("")
@require_auth
def list_my_items():
    """Every item the user owns, across cases or library-only.

    Returns all items by default (the Inventory page needs the full set for its
    totals and exports). Pass ``limit`` (and optional ``offset``) to get a
    bounded page plus a ``total`` count instead.
    """
    sb = user_client(g.access_token)
    limit, offset = parse_pagination(request.args)
    if limit is None:
        res = (
            sb.table("case_items")
            .select("*")
            .eq("user_id", g.user_id)
            .order("created_at", desc=False)
            .execute()
        )
        return jsonify({"items": res.data or []})

    res = (
        sb.table("case_items")
        .select("*", count="exact")
        .eq("user_id", g.user_id)
        .order("created_at", desc=False)
        .range(offset, offset + limit - 1)
        .execute()
    )
    return jsonify({
        "items": res.data or [],
        "total": res.count,
        "limit": limit,
        "offset": offset,
    })


@lib_bp.post("")
@require_auth
def create_library_item():
    """Create an item that may or may not be attached to a case yet."""
    data = request.get_json(silent=True) or {}
    if not data.get("name"):
        return jsonify({"error": "name is required"}), 400
    row, problem = clean_item_row(data)
    if problem:
        return jsonify({"error": problem}), 400
    row["user_id"] = g.user_id
    # If the caller didn't pass case_id, the item lives in the library only.
    sb = user_client(g.access_token)
    item, error = _insert_item(sb, row)
    if error:
        return error
    return jsonify({"item": item}), 201


@lib_bp.post("/upload-image")
@require_auth
def upload_item_image():
    """Upload an item photo and return its public URL.

    The frontend uploads the blob, gets back a URL, then stores that URL in
    one of the item's image columns (before_url / after_url) via
    create or PATCH. Keeping the upload separate means a photo can be attached
    to a draft before the item row exists.
    """
    if "image" not in request.files:
        return jsonify({"error": "image file is required"}), 400
    f = request.files["image"]
    if not f or not f.filename:
        return jsonify({"error": "image file is required"}), 400

    mime = (f.mimetype or "").lower()
    if mime not in IMAGE_EXT:
        return jsonify({"error": "unsupported image type"}), 415

    blob = f.read()
    if not blob:
        return jsonify({"error": "empty image"}), 400

    # Check the actual bytes, not just the declared type: a renamed file
    # must not end up in the public image bucket.
    from ..services.upload_validation import HEADER_LENGTH, sniff_mime

    sniffed = sniff_mime(blob[:HEADER_LENGTH])
    if sniffed not in {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}:
        return jsonify({
            "error": "That file does not look like a photo we can read. Please upload a JPG, PNG, WebP, or HEIC image."
        }), 415

    storage_path = f"{g.user_id}/{uuid.uuid4()}{IMAGE_EXT[mime]}"
    svc = service_client()
    try:
        svc.storage.from_(IMAGE_BUCKET).upload(
            storage_path, blob, {"content-type": mime, "upsert": "false"}
        )
    except Exception as exc:  # noqa: BLE001, surface the real cause
        return jsonify({"error": f"upload failed: {exc}"}), 500

    public_url = svc.storage.from_(IMAGE_BUCKET).get_public_url(storage_path)
    return jsonify({"url": public_url}), 201


@lib_bp.patch("/<item_id>")
@require_auth
def update_library_item(item_id: str):
    data = request.get_json(silent=True) or {}
    row, problem = clean_item_row(data)
    if problem:
        return jsonify({"error": problem}), 400
    if not row:
        return jsonify({"error": "no updatable fields provided"}), 400
    sb = user_client(g.access_token)
    res = (
        sb.table("case_items")
        .update(row)
        .eq("id", item_id)
        .eq("user_id", g.user_id)
        .execute()
    )
    if not res.data:
        return jsonify({"error": "not found"}), 404
    return jsonify({"item": res.data[0]})


@lib_bp.delete("/<item_id>")
@require_auth
def delete_library_item(item_id: str):
    sb = user_client(g.access_token)
    res = (
        sb.table("case_items")
        .delete()
        .eq("id", item_id)
        .eq("user_id", g.user_id)
        .execute()
    )
    if not res.data:
        return jsonify({"error": "not found"}), 404
    return jsonify({"ok": True})


@lib_bp.post("/<item_id>/attach/<case_id>")
@require_auth
def attach_item_to_case(item_id: str, case_id: str):
    """Link a library item to a case so it shows up in that case's
    recommendations and inventory view."""
    sb = user_client(g.access_token)
    res = (
        sb.table("case_items")
        .update({"case_id": case_id})
        .eq("id", item_id)
        .eq("user_id", g.user_id)
        .execute()
    )
    if not res.data:
        return jsonify({"error": "not found"}), 404
    return jsonify({"item": res.data[0]})


@lib_bp.post("/<item_id>/detach")
@require_auth
def detach_item(item_id: str):
    """Remove the case link, the item stays in the user's library."""
    sb = user_client(g.access_token)
    res = (
        sb.table("case_items")
        .update({"case_id": None})
        .eq("id", item_id)
        .eq("user_id", g.user_id)
        .execute()
    )
    if not res.data:
        return jsonify({"error": "not found"}), 404
    return jsonify({"item": res.data[0]})
