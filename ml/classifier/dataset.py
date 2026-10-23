"""
Dataset loader for the damage classification dataset.

Labels and the folder map live in `labels.py`; leak-free splitting lives in
`splits.py` (no torch there). This module only holds the torch Dataset and a
thin `build_splits` wrapper kept for callers of the old API.
"""

from pathlib import Path
from typing import Optional

from PIL import Image
from torch.utils.data import Dataset

from .labels import FOLDER_LABEL_MAP, ID2LABEL, IMAGE_EXTENSIONS, LABEL2ID  # noqa: F401
from .splits import make_splits, samples_for, write_manifest


def build_splits(
    dataset_root: str,
    val_ratio: float = 0.15,
    test_ratio: float = 0.15,
    seed: int = 42,
    manifest_path: Optional[str] = None,
    overrides_path: Optional[str] = None,
    hash_threshold: int = 10,
) -> tuple[list, list, list]:
    """Return (train, val, test) as lists of (path, label_id).

    Splits whole source-image groups, so a synthetic variant never sits across
    a split from its original. Val and test are real images only. Pass
    `manifest_path` to record group, split, and provenance for every sample.
    """
    manifest = make_splits(
        dataset_root,
        val_ratio=val_ratio,
        test_ratio=test_ratio,
        seed=seed,
        hash_threshold=hash_threshold,
        overrides_path=overrides_path,
    )
    if manifest_path:
        write_manifest(manifest, manifest_path)
    for w in manifest["meta"]["warnings"]:
        print(f"[splits] warning: {w}")
    return tuple(samples_for(manifest, sp, dataset_root) for sp in ("train", "val", "test"))


class DamageDataset(Dataset):
    """PyTorch Dataset for fire damage classification.

    Args:
        samples:   List of (image_path, label_id) from build_splits().
        processor: HuggingFace ViTImageProcessor — handles resize + normalise.
    """

    def __init__(self, samples: list[tuple[str, int]], processor):
        self.samples = samples
        self.processor = processor

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> dict:
        path, label = self.samples[idx]
        image = Image.open(path).convert("RGB")
        inputs = self.processor(images=image, return_tensors="pt")
        pixel_values = inputs["pixel_values"].squeeze(0)
        return {"pixel_values": pixel_values, "labels": label}
