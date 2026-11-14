"""
Leak-free train / val / test splitting for the damage classifier.

Why this exists (inventory.md sections 14 and 15): the old build_splits shuffled
every file together, so a `_synthetic` copy of an image could land in train while
its original sat in val. That makes validation accuracy look better than it is.

What this does instead:
  1. Groups images that come from the same source. Two images share a group when
     either (a) their filenames match once synthetic/augmentation suffixes are
     stripped and they sit in the same base folder, or (b) their content is a
     near duplicate (perceptual hash, also compared against the mirrored image so
     flipped copies are caught).
  2. Splits whole groups, never single files, with a fixed seed.
  3. Writes a manifest CSV (path, label, provenance, group, split, hash) so the
     split is reproducible and label provenance lives in data, not folder names.
  4. Can verify a manifest for leakage and flag near duplicates that carry
     different labels, which are the likely mislabels.

This module only needs Pillow and the standard library, so it runs (and is
tested) without torch.
"""

from __future__ import annotations

import csv
import random
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
SPLITS = ("train", "val", "test")
MANIFEST_FIELDS = ["path", "label", "provenance", "group", "split", "phash", "base_folder"]

# Hamming distance (out of 64 bits) at or under which two images count as the
# same source. 6 catches resizes, recompression, and mild colour changes without
# merging genuinely different photos of similar furniture.
DEFAULT_HAMMING = 6

_SYNTH_FOLDER_RE = re.compile(r"_synthetic$", re.IGNORECASE)

# Trailing markers a copy tends to pick up: "chair_01_synthetic", "chair_01_aug3",
# "chair_01 (1)", "chair_01_flip". Digits are only stripped when they follow a
# marker, so "chair_1" and "chair_2" stay different sources.
_SUFFIX_RE = re.compile(
    r"(?:[_\-\s]*(?:synthetic|synth|augmented|aug|copy|flipped|flip|rotated|rot|cropped|crop)[_\-\s]*\d*"
    r"|[_\-\s]*\(\d+\))+$",
    re.IGNORECASE,
)


@dataclass
class Record:
    path: str  # relative to dataset root, posix separators
    label: str
    provenance: str  # "original" | "synthetic"
    base_folder: str  # rel folder with any _synthetic suffix removed
    phash: int = 0
    group: str = ""
    split: str = ""


# --------------------------------------------------------------------------
# hashing
# --------------------------------------------------------------------------

def dhash(image: Image.Image, size: int = 8) -> int:
    """64-bit difference hash. Compares each pixel to its right neighbour."""
    small = image.convert("L").resize((size + 1, size), Image.LANCZOS)
    pixels = small.tobytes()  # mode L: one byte per pixel
    bits = 0
    for row in range(size):
        for col in range(size):
            left = pixels[row * (size + 1) + col]
            right = pixels[row * (size + 1) + col + 1]
            bits = (bits << 1) | (1 if left > right else 0)
    return bits


def flip_invariant_hash(image: Image.Image) -> int:
    """Hash that is the same for an image and its horizontal mirror."""
    return min(dhash(image), dhash(ImageOps.mirror(image)))


def hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


# --------------------------------------------------------------------------
# naming
# --------------------------------------------------------------------------

def split_folder(rel_folder: str) -> tuple[str, str]:
    """('chair_damaged/damaged_synthetic') -> ('chair_damaged/damaged', 'synthetic')."""
    if _SYNTH_FOLDER_RE.search(rel_folder):
        return _SYNTH_FOLDER_RE.sub("", rel_folder), "synthetic"
    return rel_folder, "original"


def normalized_stem(filename: str) -> str:
    stem = Path(filename).stem.lower().strip()
    stripped = _SUFFIX_RE.sub("", stem)
    return stripped or stem


def source_key(base_folder: str, filename: str) -> str:
    return f"{base_folder}::{normalized_stem(filename)}"


# --------------------------------------------------------------------------
# grouping
# --------------------------------------------------------------------------

class _UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def collect_records(dataset_root: str, folder_label_map: dict[str, str]) -> tuple[list[Record], list[str]]:
    """Walk the folder map, hash every image. Returns (records, unreadable_paths)."""
    root = Path(dataset_root)
    records: list[Record] = []
    unreadable: list[str] = []

    for rel_folder, label in folder_label_map.items():
        folder = root / rel_folder
        if not folder.exists():
            continue
        base_folder, provenance = split_folder(rel_folder)
        for f in sorted(folder.iterdir()):
            if f.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            try:
                with Image.open(f) as img:
                    img = ImageOps.exif_transpose(img)
                    h = flip_invariant_hash(img)
            except Exception:
                unreadable.append(str(f))
                continue
            records.append(
                Record(
                    path=(Path(rel_folder) / f.name).as_posix(),
                    label=label,
                    provenance=provenance,
                    base_folder=base_folder,
                    phash=h,
                )
            )
    return records, unreadable


def assign_groups(records: list[Record], max_hamming: int = DEFAULT_HAMMING) -> None:
    """Fill record.group in place. Groups are named after their first member."""
    n = len(records)
    uf = _UnionFind(n)

    # (a) same source by filename within the same base folder
    by_key: dict[str, int] = {}
    for i, r in enumerate(records):
        key = source_key(r.base_folder, Path(r.path).name)
        if key in by_key:
            uf.union(by_key[key], i)
        else:
            by_key[key] = i

    # (b) near-duplicate content, across folders and labels. O(n^2) on 64-bit
    # ints, fine for a few thousand images.
    hashes = [r.phash for r in records]
    for i in range(n):
        hi = hashes[i]
        for j in range(i + 1, n):
            if (hi ^ hashes[j]).bit_count() <= max_hamming:
                uf.union(i, j)

    names: dict[int, str] = {}
    for i, r in enumerate(records):
        root = uf.find(i)
        if root not in names:
            names[root] = f"g{len(names):05d}"
        r.group = names[root]


def split_groups(
    records: list[Record],
    val_ratio: float = 0.15,
    test_ratio: float = 0.15,
    seed: int = 42,
) -> None:
    """Assign record.split by whole group, roughly balancing classes per split."""
    if not 0 < val_ratio < 1 or not 0 < test_ratio < 1 or val_ratio + test_ratio >= 1:
        raise ValueError("val_ratio and test_ratio must be in (0, 1) and sum to less than 1")

    targets = {"train": 1 - val_ratio - test_ratio, "val": val_ratio, "test": test_ratio}

    groups: dict[str, list[Record]] = defaultdict(list)
    for r in records:
        groups[r.group].append(r)

    label_totals = Counter(r.label for r in records)
    counts = {s: Counter() for s in SPLITS}

    ids = sorted(groups)
    rng = random.Random(seed)
    rng.shuffle(ids)
    ids.sort(key=lambda g: len(groups[g]), reverse=True)  # big groups first, ties stay shuffled

    for gid in ids:
        members = groups[gid]
        group_labels = Counter(m.label for m in members)

        def need(split: str) -> float:
            # how far below its target share this split is, weighted over the
            # labels this group would add
            total = 0.0
            for label, k in group_labels.items():
                want = targets[split] * label_totals[label]
                total += (want - counts[split][label]) / max(label_totals[label], 1) * k
            return total

        best = max(SPLITS, key=lambda s: (need(s), targets[s]))
        for m in members:
            m.split = best
            counts[best][m.label] += 1


# --------------------------------------------------------------------------
# manifest
# --------------------------------------------------------------------------

def write_manifest(records: list[Record], manifest_path: str) -> None:
    Path(manifest_path).parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        for r in sorted(records, key=lambda r: r.path):
            writer.writerow(
                {
                    "path": r.path,
                    "label": r.label,
                    "provenance": r.provenance,
                    "group": r.group,
                    "split": r.split,
                    "phash": f"{r.phash:016x}",
                    "base_folder": r.base_folder,
                }
            )


def read_manifest(manifest_path: str) -> list[Record]:
    records: list[Record] = []
    with open(manifest_path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            records.append(
                Record(
                    path=row["path"],
                    label=row["label"],
                    provenance=row["provenance"],
                    base_folder=row["base_folder"],
                    phash=int(row["phash"], 16),
                    group=row["group"],
                    split=row["split"],
                )
            )
    return records


# --------------------------------------------------------------------------
# checks
# --------------------------------------------------------------------------

def find_leaks(records: list[Record], max_hamming: int = DEFAULT_HAMMING) -> list[str]:
    """Human-readable problems. Empty list means the split is clean."""
    problems: list[str] = []

    group_splits: dict[str, set[str]] = defaultdict(set)
    for r in records:
        group_splits[r.group].add(r.split)
    for gid, splits in sorted(group_splits.items()):
        if len(splits) > 1:
            problems.append(f"group {gid} spans splits {sorted(splits)}")

    # belt and braces: re-check content across splits, independent of grouping
    for i, a in enumerate(records):
        for b in records[i + 1:]:
            if a.split != b.split and hamming(a.phash, b.phash) <= max_hamming:
                problems.append(
                    f"near duplicate across splits: {a.path} ({a.split}) ~ {b.path} ({b.split})"
                )
    return problems


def label_conflicts(records: list[Record]) -> list[tuple[str, list[Record]]]:
    """Groups whose members carry more than one label.

    A synthetic copy keeps its original's label, so a conflict usually means a
    file was filed in the wrong folder. These are the first things to review
    when auditing table_intact.
    """
    groups: dict[str, list[Record]] = defaultdict(list)
    for r in records:
        groups[r.group].append(r)
    out = []
    for gid, members in sorted(groups.items()):
        if len({m.label for m in members}) > 1:
            out.append((gid, sorted(members, key=lambda m: m.path)))
    return out


def summarize(records: list[Record]) -> str:
    lines = ["split   total  " + "  ".join(f"{l:>11}" for l in sorted({r.label for r in records}))]
    labels = sorted({r.label for r in records})
    for s in SPLITS:
        rows = [r for r in records if r.split == s]
        c = Counter(r.label for r in rows)
        lines.append(f"{s:<7} {len(rows):>5}  " + "  ".join(f"{c[l]:>11}" for l in labels))
    n_groups = len({r.group for r in records})
    n_synth = sum(1 for r in records if r.provenance == "synthetic")
    lines.append(f"{len(records)} images, {n_groups} source groups, {n_synth} synthetic")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# entry point used by dataset.build_splits
# --------------------------------------------------------------------------

def build_manifest(
    dataset_root: str,
    folder_label_map: dict[str, str],
    manifest_path: str,
    val_ratio: float = 0.15,
    test_ratio: float = 0.15,
    seed: int = 42,
    max_hamming: int = DEFAULT_HAMMING,
) -> list[Record]:
    records, unreadable = collect_records(dataset_root, folder_label_map)
    if unreadable:
        print(f"warning: skipped {len(unreadable)} unreadable image(s), first: {unreadable[0]}")
    if not records:
        raise RuntimeError(f"no images found under {dataset_root}")
    assign_groups(records, max_hamming=max_hamming)
    split_groups(records, val_ratio=val_ratio, test_ratio=test_ratio, seed=seed)

    problems = find_leaks(records, max_hamming=max_hamming)
    if problems:
        raise RuntimeError("split still leaks:\n" + "\n".join(problems[:10]))

    write_manifest(records, manifest_path)
    return records


MANIFEST_NAME = "split_manifest.csv"


def default_manifest_path(dataset_root: str) -> str:
    return str(Path(dataset_root) / MANIFEST_NAME)


def load_records(
    dataset_root: str,
    manifest_path: str | None = None,
    val_ratio: float = 0.15,
    test_ratio: float = 0.15,
    seed: int = 42,
    rebuild: bool = False,
) -> list[Record]:
    """Read the manifest, building it first if it does not exist yet.

    An existing manifest is reused as is, so the test set stays fixed between
    runs. Pass rebuild=True (or delete the file) to re-split on purpose.
    """
    from .labels import FOLDER_LABEL_MAP

    manifest_path = manifest_path or default_manifest_path(dataset_root)
    if Path(manifest_path).exists() and not rebuild:
        return read_manifest(manifest_path)
    return build_manifest(
        dataset_root,
        FOLDER_LABEL_MAP,
        manifest_path,
        val_ratio=val_ratio,
        test_ratio=test_ratio,
        seed=seed,
    )
