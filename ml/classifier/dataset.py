"""
Dataset loader for the fire damage classification dataset.

Expected directory layout (relative to dataset_root):
    chair_intact/                        → intact
    chair_intact_synthetic/              → intact
    chair_damaged/damaged/               → destroyed
    chair_damaged/damaged_synthetic/     → destroyed
    chair_damaged/salvageable/           → salvageable
    chair_damaged/salvageable_synthetic/ → salvageable
    table_intact/                        → intact (⚠ some filenames look damaged — verify)
    table_damaged/damaged/               → destroyed
    table_damaged/damaged_synthetic/     → destroyed
    table_damaged/salvageable/           → salvageable
    table_damaged/salvageable_synthetic/ → salvageable

Splits are made by source group, not by file, and written to a manifest CSV
(see splits.py). Synthetic copies always stay with their original.
"""

import random
from pathlib import Path

from PIL import Image, ImageEnhance, ImageOps
from torch.utils.data import Dataset

from . import splits as splits_mod
from .labels import FOLDER_LABEL_MAP, ID2LABEL, LABEL2ID  # noqa: F401  (re-exported)

IMAGE_EXTENSIONS = splits_mod.IMAGE_EXTENSIONS
MANIFEST_NAME = splits_mod.MANIFEST_NAME
load_records = splits_mod.load_records
default_manifest_path = splits_mod.default_manifest_path


def build_splits(
    dataset_root: str,
    val_ratio: float = 0.15,
    test_ratio: float = 0.15,
    seed: int = 42,
    manifest_path: str | None = None,
    rebuild: bool = False,
) -> tuple[list, list, list]:
    """Return (train, val, test) as lists of (absolute_path, label_id)."""
    records = load_records(
        dataset_root,
        manifest_path=manifest_path,
        val_ratio=val_ratio,
        test_ratio=test_ratio,
        seed=seed,
        rebuild=rebuild,
    )
    root = Path(dataset_root)
    out: dict[str, list[tuple[str, int]]] = {"train": [], "val": [], "test": []}
    for r in records:
        out[r.split].append((str(root / r.path), LABEL2ID[r.label]))
    return out["train"], out["val"], out["test"]


def _augment(image: Image.Image, rng: random.Random) -> Image.Image:
    """Light, label-preserving augmentation. Training split only."""
    if rng.random() < 0.5:
        image = ImageOps.mirror(image)
    # small brightness and contrast shifts; strong shifts could fake or hide char
    image = ImageEnhance.Brightness(image).enhance(rng.uniform(0.9, 1.1))
    image = ImageEnhance.Contrast(image).enhance(rng.uniform(0.9, 1.1))
    return image


class DamageDataset(Dataset):
    """PyTorch Dataset for fire damage classification.

    Args:
        samples:   List of (image_path, label_id) from build_splits().
        processor: HuggingFace ViTImageProcessor — handles resize + normalise.
        augment:   Apply light augmentation. Only ever True for the train split.
    """

    def __init__(self, samples: list[tuple[str, int]], processor, augment: bool = False):
        self.samples = samples
        self.processor = processor
        self.augment = augment
        self._rng = random.Random()

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> dict:
        path, label = self.samples[idx]
        image = Image.open(path)
        image = ImageOps.exif_transpose(image).convert("RGB")
        if self.augment:
            image = _augment(image, self._rng)
        inputs = self.processor(images=image, return_tensors="pt")
        pixel_values = inputs["pixel_values"].squeeze(0)
        return {"pixel_values": pixel_values, "labels": label}
