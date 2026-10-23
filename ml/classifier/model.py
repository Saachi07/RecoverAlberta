"""
ViT fine-tune wrapper for 3-class fire damage classification.

Model: google/vit-base-patch16-224
Classes: intact (0) | salvageable (1) | destroyed (2)

We replace the ViT classification head with a 3-class head and fine-tune
the full model (or freeze the encoder — see train.py).
"""

from transformers import ViTForImageClassification, ViTImageProcessor

from .labels import ID2LABEL, LABEL2ID

MODEL_NAME = "google/vit-base-patch16-224"


def load_model() -> tuple[ViTForImageClassification, ViTImageProcessor]:
    """Download / load the ViT model with a fresh 3-class head."""
    processor = ViTImageProcessor.from_pretrained(MODEL_NAME)

    model = ViTForImageClassification.from_pretrained(
        MODEL_NAME,
        num_labels=len(LABEL2ID),
        id2label=ID2LABEL,
        label2id=LABEL2ID,
        ignore_mismatched_sizes=True,  # replaces the pretrained 1000-class head
    )

    return model, processor


def load_finetuned(checkpoint_dir: str) -> tuple[ViTForImageClassification, ViTImageProcessor]:
    """Load a previously saved fine-tuned model from disk."""
    processor = ViTImageProcessor.from_pretrained(checkpoint_dir)
    model = ViTForImageClassification.from_pretrained(checkpoint_dir)
    return model, processor
