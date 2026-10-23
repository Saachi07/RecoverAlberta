"""
Run the fine-tuned damage classifier on a single image crop.

This is the function damage_analyzer.py will call once the model is trained.
The bounding boxes from Gemini are used to crop the item before calling this.
"""

import torch
from PIL import Image

from .labels import ID2LABEL
from .model import load_finetuned

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# Module-level cache so the model loads once per process
_model = None
_processor = None


def _load(checkpoint_dir: str):
    global _model, _processor
    if _model is None:
        _model, _processor = load_finetuned(checkpoint_dir)
        _model.to(DEVICE)
        _model.eval()


def predict_damage(
    image_path: str,
    checkpoint_dir: str = "./checkpoints",
    bounding_box: dict | None = None,
) -> dict:
    """Classify a furniture item as intact / salvageable / destroyed.

    Args:
        image_path:     Path to the post-disaster photo.
        checkpoint_dir: Directory containing the saved fine-tuned model.
        bounding_box:   Optional crop region from Gemini's damage analysis.
                        Dict with keys x1, y1, x2, y2 (normalised 0-1000).
                        If None, classifies the full image.

    Returns:
        {
            "damage_grade": "intact" | "salvageable" | "destroyed",
            "confidence": float,
            "scores": {"intact": float, "salvageable": float, "destroyed": float}
        }
    """
    _load(checkpoint_dir)

    image = Image.open(image_path).convert("RGB")

    if bounding_box:
        w, h = image.size
        x1 = int(bounding_box["x1"] / 1000 * w)
        y1 = int(bounding_box["y1"] / 1000 * h)
        x2 = int(bounding_box["x2"] / 1000 * w)
        y2 = int(bounding_box["y2"] / 1000 * h)
        image = image.crop((x1, y1, x2, y2))

    inputs = _processor(images=image, return_tensors="pt")
    pixel_values = inputs["pixel_values"].to(DEVICE)

    with torch.no_grad():
        logits = _model(pixel_values=pixel_values).logits
        probs = torch.softmax(logits, dim=-1).squeeze(0)

    pred_id = probs.argmax().item()
    return {
        "damage_grade": ID2LABEL[pred_id],
        "confidence": round(probs[pred_id].item(), 4),
        "scores": {ID2LABEL[i]: round(p.item(), 4) for i, p in enumerate(probs)},
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m classifier.predict <image_path> [checkpoint_dir]")
        sys.exit(1)

    img = sys.argv[1]
    ckpt = sys.argv[2] if len(sys.argv) > 2 else "./checkpoints"
    result = predict_damage(img, checkpoint_dir=ckpt)
    print(result)
