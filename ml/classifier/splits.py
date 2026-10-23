"""Leak-free train/val/test splits for the damage classifier (inventory.md s15).

The old `build_splits` shuffled every file together, so a `_synthetic` variant
of an image could sit in train while its original sat in val. This module:

1. Collects samples with provenance (folder, synthetic or real, label source).
2. Groups samples that come from the same source image: first by normalized
   filename (synthetic and augmentation markers stripped), then by perceptual
   hash across the whole pool (mirror-invariant), merged with union-find.
3. Splits whole groups, stratified by label, with a fixed seed.
4. Keeps val and test 100 percent real. Synthetic variants of a group that
   lands in val or test are dropped, not trained on. Groups with no real image
   go to train.
5. Writes a manifest (JSON) so every sample's group, split, and provenance is
   recorded instead of living in folder names.

No torch import: usable from tests, audits, and notebooks.

Limits: the name and hash heuristics catch re-encodes, flips, and light edits.
Heavy augmentation (large crops, colour changes) can slip past a 64-bit hash.
If the manifest report shows suspiciously high val accuracy, add an embedding
similarity pass before trusting it.
"""

from __future__ import annotations

import csv
import json
import random
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from .labels import FOLDER_LABEL_MAP, IMAGE_EXTENSIONS, LABEL2ID

SPLITS = ("train", "val", "test")
DROPPED = "dropped"
DROP_LABEL = "drop"  # override label that removes a sample entirely

# Tokens that mark a file as a derived copy of another image. Matched only
# when delimited by _ - space or string edges, so "synergy" is untouched.
_DERIVED_TOKENS = (
    "synthetic|synth|syn|augmented|aug|copy|flip|flipped|mirror|mirrored|"
    "rot|rotate|rotated|bright|brighter|dark|darker|noise|noisy|blur|blurred|"
    "crop|cropped|zoom|jitter"
)
_DERIVED_RE = re.compile(
    rf"(?:^|[_\-\s])(?:{_DERIVED_TOKENS})(?:[_\-\s]?\d+)?(?=$|[_\-\s])",
    re.IGNORECASE,
)
_COPY_SUFFIX_RE = re.compile(r"\s*\(\d+\)$")


def source_key(stem: str) -> str:
    """Filename stem with derived-copy markers removed.

    "chair_12_synthetic_3" -> "chair_12"; "chair_12_flip" -> "chair_12".
    """
    s = stem.lower()
    prev = None
    while prev != s:  # markers can stack: chair_12_aug3_flip
        prev = s
        s = _DERIVED_RE.sub("", s)
        s = _COPY_SUFFIX_RE.sub("", s)
    s = s.strip(" _-")
    return s or stem.lower()


@dataclass
class Sample:
    rel_path: str  # posix, relative to dataset_root
    label: str
    folder: str
    item_type: str
    synthetic: bool
    label_source: str = "folder"  # folder | override
    group: str = ""
    split: str = ""
    phash: Optional[str] = None  # hex, for the manifest

    def abs_path(self, root: str | Path) -> str:
        return str(Path(root) / self.rel_path)


# ---------------------------------------------------------------- collection


def load_overrides(path: str | Path) -> dict[str, str]:
    """CSV with columns rel_path,label[,note]. label is a class or "drop"."""
    out: dict[str, str] = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            rel = (row.get("rel_path") or "").strip().replace("\\", "/")
            label = (row.get("label") or "").strip().lower()
            if not rel:
                continue
            if label != DROP_LABEL and label not in LABEL2ID:
                raise ValueError(f"override for {rel!r} has unknown label {label!r}")
            out[rel] = label
    return out


def collect_samples(
    dataset_root: str | Path,
    overrides: Optional[dict[str, str]] = None,
) -> list[Sample]:
    root = Path(dataset_root)
    overrides = overrides or {}
    samples: list[Sample] = []
    for rel_folder in sorted(FOLDER_LABEL_MAP):
        folder = root / rel_folder
        if not folder.exists():
            continue
        folder_label = FOLDER_LABEL_MAP[rel_folder]
        synthetic = "synthetic" in rel_folder.lower()
        item_type = rel_folder.split("/")[0].split("_")[0]
        for f in sorted(folder.iterdir()):
            if f.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            rel = f.relative_to(root).as_posix()
            label, src = folder_label, "folder"
            if rel in overrides:
                if overrides[rel] == DROP_LABEL:
                    continue
                label, src = overrides[rel], "override"
            samples.append(
                Sample(
                    rel_path=rel,
                    label=label,
                    folder=rel_folder,
                    item_type=item_type,
                    synthetic=synthetic,
                    label_source=src,
                )
            )
    return samples


# ------------------------------------------------------------------- hashing

_MIN_STD = 4.0  # near-uniform images all hash alike; do not link on them


def dhash_pair(path: str, size: int = 8) -> Optional[tuple[int, int]]:
    """64-bit difference hash of the image and of its horizontal mirror.

    Returns None if the file cannot be read or is near-uniform.
    """
    try:
        import numpy as np
        from PIL import Image, ImageOps

        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im).convert("L")
            small = im.resize((size + 1, size), Image.LANCZOS)
        arr = np.asarray(small, dtype=np.float32)
        if float(arr.std()) < _MIN_STD:
            return None

        def bits(a) -> int:
            diff = a[:, 1:] > a[:, :-1]
            value = 0
            for b in diff.flatten():
                value = (value << 1) | int(b)
            return value

        return bits(arr), bits(arr[:, ::-1])
    except Exception:  # noqa: BLE001 - unreadable file is reported, not fatal
        return None


def _popcount(x: int) -> int:
    return bin(x).count("1")


class _UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def assign_groups(
    samples: list[Sample],
    dataset_root: str | Path,
    hash_threshold: int = 10,
    use_hash: bool = True,
) -> dict:
    """Fill sample.group in place. Returns a small report dict."""
    n = len(samples)
    uf = _UnionFind(n)

    by_name: dict[tuple[str, str], int] = {}
    for i, s in enumerate(samples):
        key = (s.item_type, source_key(Path(s.rel_path).stem))
        if key in by_name:
            uf.union(by_name[key], i)
        else:
            by_name[key] = i

    unhashable: list[str] = []
    hash_links = 0
    if use_hash:
        hashes: list[Optional[tuple[int, int]]] = []
        for s in samples:
            h = dhash_pair(s.abs_path(dataset_root))
            hashes.append(h)
            if h is None:
                unhashable.append(s.rel_path)
            else:
                s.phash = f"{h[0]:016x}"
        for i in range(n):
            hi = hashes[i]
            if hi is None:
                continue
            for j in range(i + 1, n):
                hj = hashes[j]
                if hj is None or uf.find(i) == uf.find(j):
                    continue
                if samples[i].item_type != samples[j].item_type:
                    continue
                d = min(_popcount(hi[0] ^ hj[0]), _popcount(hi[0] ^ hj[1]))
                if d <= hash_threshold:
                    uf.union(i, j)
                    hash_links += 1

    roots: dict[int, str] = {}
    for i, s in enumerate(samples):
        r = uf.find(i)
        if r not in roots:
            roots[r] = f"g{len(roots):05d}"
        s.group = roots[r]

    sizes = Counter(s.group for s in samples)
    return {
        "n_groups": len(sizes),
        "largest_group": max(sizes.values()) if sizes else 0,
        "hash_links": hash_links,
        "unhashable": unhashable,
    }


# ----------------------------------------------------------------- splitting


def _group_table(samples: list[Sample]) -> dict[str, dict]:
    table: dict[str, dict] = {}
    for s in samples:
        g = table.setdefault(s.group, {"real": Counter(), "all": Counter(), "n_real": 0})
        g["all"][s.label] += 1
        if not s.synthetic:
            g["real"][s.label] += 1
            g["n_real"] += 1
    return table


def _majority(counter: Counter) -> str:
    top = max(counter.values())
    return sorted(k for k, v in counter.items() if v == top)[0]


def split_groups(
    samples: list[Sample],
    val_ratio: float,
    test_ratio: float,
    seed: int,
) -> dict[str, str]:
    """Assign each group to train, val, or test. Stratified by label, by real
    sample count (val and test hold real images only)."""
    if val_ratio < 0 or test_ratio < 0 or val_ratio + test_ratio >= 1:
        raise ValueError("val_ratio + test_ratio must be in [0, 1)")

    table = _group_table(samples)
    assignment: dict[str, str] = {}
    eligible: list[str] = []
    for gid, info in table.items():
        if info["n_real"] == 0:
            assignment[gid] = "train"  # synthetic-only: never evaluate on it
        else:
            eligible.append(gid)

    real_per_label: Counter = Counter()
    for gid in eligible:
        real_per_label[_majority(table[gid]["real"])] += table[gid]["n_real"]

    target = {
        "val": {l: val_ratio * c for l, c in real_per_label.items()},
        "test": {l: test_ratio * c for l, c in real_per_label.items()},
        "train": {l: (1 - val_ratio - test_ratio) * c for l, c in real_per_label.items()},
    }
    got = {s: Counter() for s in SPLITS}

    rng = random.Random(seed)
    order = sorted(eligible)
    rng.shuffle(order)
    order.sort(key=lambda g: -table[g]["n_real"])  # stable: big groups first

    pref = {"val": 0, "test": 1, "train": 2}
    for gid in order:
        label = _majority(table[gid]["real"])
        size = table[gid]["n_real"]
        best, best_score = "train", None
        for split in sorted(SPLITS, key=pref.get):
            t = target[split].get(label, 0.0)
            if t <= 0:
                continue
            score = (t - got[split][label]) / t
            if best_score is None or score > best_score:
                best, best_score = split, score
        assignment[gid] = best
        got[best][label] += size
    return assignment


# ------------------------------------------------------------------ manifest


def make_splits(
    dataset_root: str | Path,
    val_ratio: float = 0.15,
    test_ratio: float = 0.15,
    seed: int = 42,
    hash_threshold: int = 10,
    use_hash: bool = True,
    overrides_path: Optional[str | Path] = None,
) -> dict:
    """Build the full manifest: {"meta": {...}, "entries": [...]}."""
    overrides = load_overrides(overrides_path) if overrides_path else {}
    samples = collect_samples(dataset_root, overrides)
    if not samples:
        raise FileNotFoundError(f"no images found under {dataset_root}")

    group_report = assign_groups(samples, dataset_root, hash_threshold, use_hash)
    assignment = split_groups(samples, val_ratio, test_ratio, seed)

    for s in samples:
        gsplit = assignment[s.group]
        s.split = DROPPED if (s.synthetic and gsplit != "train") else gsplit

    conflicts: dict[str, list[str]] = defaultdict(list)
    labels_by_group: dict[str, set] = defaultdict(set)
    for s in samples:
        labels_by_group[s.group].add(s.label)
    for s in samples:
        if len(labels_by_group[s.group]) > 1:
            conflicts[s.group].append(f"{s.rel_path} [{s.label}]")

    counts = {sp: Counter() for sp in (*SPLITS, DROPPED)}
    for s in samples:
        counts[s.split][s.label] += 1

    warnings: list[str] = []
    for sp in ("val", "test"):
        for label in LABEL2ID:
            if counts[sp][label] == 0:
                warnings.append(f"{sp} has no {label!r} samples")
    if group_report["largest_group"] > 0.2 * len(samples):
        warnings.append(
            f"largest group has {group_report['largest_group']} samples "
            f"(>20% of pool); hash threshold may be too loose"
        )
    if conflicts:
        warnings.append(
            f"{len(conflicts)} groups mix labels (same source image under more "
            f"than one label); review before trusting metrics"
        )

    return {
        "meta": {
            "seed": seed,
            "val_ratio": val_ratio,
            "test_ratio": test_ratio,
            "hash_threshold": hash_threshold,
            "use_hash": use_hash,
            "overrides": len(overrides),
            "n_samples": len(samples),
            **{k: v for k, v in group_report.items() if k != "unhashable"},
            "n_unhashable": len(group_report["unhashable"]),
            "counts": {sp: dict(c) for sp, c in counts.items()},
            "label_conflicts": dict(conflicts),
            "warnings": warnings,
        },
        "entries": [asdict(s) for s in samples],
    }


def write_manifest(manifest: dict, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1, sort_keys=True)


def load_manifest(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def samples_for(
    manifest: dict, split: str, dataset_root: str | Path
) -> list[tuple[str, int]]:
    """(abs_path, label_id) pairs for one split."""
    root = Path(dataset_root)
    return [
        (str(root / e["rel_path"]), LABEL2ID[e["label"]])
        for e in manifest["entries"]
        if e["split"] == split
    ]
