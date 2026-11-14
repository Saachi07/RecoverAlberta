import json
import os
import tempfile

from flask import Flask, jsonify, request

from analyzer import analyze_room_photo
from loss_report import generate_loss_report
from yolo_detector import detect_furniture

app = Flask(__name__)


def _save_upload(file) -> str:
    filename = file.filename or ""
    suffix = os.path.splitext(filename)[1] or ".jpg"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    file.save(tmp.name)
    tmp.close()
    return tmp.name


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/ml/analyze-photo", methods=["POST"])
def analyze_photo():
    """Before-disaster photo → structured room inventory with CAD price estimates."""
    if "image" not in request.files:
        return jsonify({"error": "No image file provided"}), 400

    tmp_path = _save_upload(request.files["image"])
    try:
        result = analyze_room_photo(tmp_path)
        return jsonify(result.model_dump())
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        os.unlink(tmp_path)


@app.route("/ml/analyze-damage", methods=["POST"])
def analyze_damage():
    """Post-disaster photo + pre-disaster inventory → per-item salvageable/damaged counts.

    Form fields:
      image         — post-disaster image file
      pre_inventory — JSON string from /ml/analyze-photo
    """
    if "image" not in request.files:
        return jsonify({"error": "No image file provided"}), 400
    if "pre_inventory" not in request.form:
        return jsonify({"error": "pre_inventory JSON required"}), 400

    try:
        pre_inventory = json.loads(request.form["pre_inventory"])
    except json.JSONDecodeError:
        return jsonify({"error": "pre_inventory must be valid JSON"}), 400

    tmp_path = _save_upload(request.files["image"])
    try:
        items = pre_inventory.get("items", [])
        labels = list({item["yolo_label"] for item in items})

        detected = detect_furniture(tmp_path, labels)

        label_remaining = {label: detected.get(label, 0) for label in labels}
        result_items = []

        for item in items:
            label = item["yolo_label"]
            pre_count = item.get("count", 1)
            available = label_remaining.get(label, 0)
            salvageable = min(available, pre_count)
            damaged = pre_count - salvageable
            label_remaining[label] = max(0, available - salvageable)

            if damaged == 0:
                status = "safe"
            elif salvageable == 0:
                status = "damaged"
            else:
                status = "partial"

            result_items.append({
                **item,
                "pre_count": pre_count,
                "salvageable_count": salvageable,
                "damaged_count": damaged,
                "status": status,
            })

        return jsonify({
            "room_type": pre_inventory.get("room_type", "other"),
            "items": result_items,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        os.unlink(tmp_path)


@app.route("/ml/loss-report", methods=["POST"])
def loss_report():
    """Before inventory + after damage assessment → itemised loss report with CAD totals.

    Body (JSON):
    {
        "before_inventory": { ...output from /ml/analyze-photo... },
        "after_damage":     { ...output from /ml/analyze-damage... }
    }
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    before_inventory = data.get("before_inventory")
    after_damage = data.get("after_damage")

    if not before_inventory or not after_damage:
        return jsonify({"error": "Both before_inventory and after_damage are required"}), 400

    try:
        result = generate_loss_report(before_inventory, after_damage)
        return jsonify(result.model_dump())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(
        debug=os.environ.get("FLASK_DEBUG", "False").lower() == "true", 
        port=5001, 
        use_reloader=False
    )
