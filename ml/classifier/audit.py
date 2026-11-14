"""
Label audit for the damage classifier (inventory.md section 15, step 3).

Usage:
    python -m classifier.audit --dataset ../../dataset
    python -m classifier.audit --dataset ../../dataset --checkpoint ./checkpoints --split val

Three checks, cheapest first:
  1. Filenames in an "intact" folder that sound damaged (and the reverse). This
     is where the table_intact TODO came from.
  2. Near-duplicate images that carry different labels. A copy keeps its
     original's label, so a conflict almost always means a misfiled image.
  3. With --checkpoint: images the trained model gets wrong with high
     confidence. Often the model is right and the label is wrong. Review the
     image, fix the folder, then rebuild the manifest.

The test split is never audited: looking at it to fix labels would leak it into
your decisions. Only train and val are allowed.

Nothing here moves or edits files. It prints what to look at.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from . import splits as S

DAMAGE_WORDS = re.compile(
    r"(burn|burnt|char|fire|soot|ash|scorch|melt|smoke|destroy|wreck|ruin|damag|broken|collaps)",
    re.IGNORECASE,
)
INTACT_WORDS = re.compile(r"(intact|undamaged|pristine|clean|new|before)", re.IGNORECASE)


def filename_flags(records: list[S.Record]) -> list[tuple[S.Record, str]]:
    """Files whose name disagrees with the folder they were filed under."""
    flags = []
    for r in records:
        name = Path(r.path).stem
        if r.label == "intact" and DAMAGE_WORDS.search(name):
            flags.append((r, "filed as intact but the name sounds damaged"))
        elif r.label != "intact" and INTACT_WORDS.search(name):
            flags.append((r, f"filed as {r.label} but the name sounds intact"))
    return flags


def confident_errors(
    dataset_root: str,
    records: list[S.Record],
    checkpoint_dir: str,
    split: str,
    min_conf: float,
) -> list[tuple[S.Record, str, float]]:
    """Predictions that disagree with the label at confidence >= min_conf."""
    import torch  # imported here so the cheap checks work without torch

    from .labels import ID2LABEL
    from .model import load_finetuned
    from PIL import Image, ImageOps

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model, processor = load_finetuned(checkpoint_dir)
    model.to(device).eval()

    root = Path(dataset_root)
    todo = [r for r in records if r.split == split]
    out: list[tuple[S.Record, str, float]] = []
    batch_size = 16
    for i in range(0, len(todo), batch_size):
        chunk = todo[i : i + batch_size]
        images = []
        for r in chunk:
            img = ImageOps.exif_transpose(Image.open(root / r.path)).convert("RGB")
            images.append(img)
        inputs = processor(images=images, return_tensors="pt")
        with torch.no_grad():
            probs = torch.softmax(model(pixel_values=inputs["pixel_values"].to(device)).logits, dim=-1)
        conf, pred = probs.max(dim=-1)
        for r, c, p in zip(chunk, conf.tolist(), pred.tolist()):
            guess = ID2LABEL[p]
            if guess != r.label and c >= min_conf:
                out.append((r, guess, c))
    out.sort(key=lambda t: -t[2])
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--manifest", default=None, help="defaults to <dataset>/split_manifest.csv")
    ap.add_argument("--checkpoint", default=None, help="also list confidently wrong predictions")
    ap.add_argument("--split", choices=["train", "val"], default="val")
    ap.add_argument("--min-conf", type=float, default=0.9)
    args = ap.parse_args()

    records = S.load_records(args.dataset, manifest_path=args.manifest)
    print(S.summarize(records))

    print("\n1. filename vs folder")
    flags = filename_flags(records)
    if not flags:
        print("   nothing flagged")
    for r, why in flags:
        print(f"   {r.path}  ({why})")

    print("\n2. near duplicates with different labels")
    conflicts = S.label_conflicts(records)
    if not conflicts:
        print("   none")
    for gid, members in conflicts:
        print(f"   {gid}:")
        for m in members:
            print(f"      {m.label:<12} {m.path}")

    if args.checkpoint:
        print(f"\n3. confidently wrong on {args.split} (conf >= {args.min_conf})")
        errs = confident_errors(args.dataset, records, args.checkpoint, args.split, args.min_conf)
        if not errs:
            print("   none")
        for r, guess, c in errs:
            print(f"   {c:.3f}  labelled {r.label:<12} model says {guess:<12} {r.path}")

    print(
        "\nFix any misfiled images by moving them to the right folder, then rebuild the split "
        "(delete split_manifest.csv or pass rebuild=True). Rebuilding changes the test set, so "
        "do it before you start comparing runs, not after."
    )


if __name__ == "__main__":
    main()
