"""Label audit tools (inventory.md s15 step 3).

    python -m classifier.audit table-intact --dataset D --out table_intact_review.csv
    python -m classifier.audit conflicts --manifest checkpoints/split_manifest.json
    python -m classifier.audit confident-wrong --dataset D --manifest M \
        --checkpoint checkpoints --out confident_wrong.csv

Workflow: review each CSV by hand, fill `new_label` (intact, salvageable,
destroyed, or drop) and `note` for rows that are wrong, then copy those rows
(rel_path,label,note) into label_overrides.csv and pass it to train with
--overrides. Files never move; the override is the provenance record.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

from .labels import ID2LABEL, IMAGE_EXTENSIONS

# Filename tokens that suggest damage. A hit in an "intact" folder is a
# candidate mislabel, not proof: a human decides.
SUSPECT_TOKENS = re.compile(
    r"(damag|burn|burnt|fire|char|ash|soot|destroy|ruin|wreck|broken|salvage|"
    r"melt|smok|flood|water)",
    re.IGNORECASE,
)

REVIEW_FIELDS = ["rel_path", "reason", "current_label", "new_label", "note"]


def _write_csv(path: str, rows: list[dict], fields: list[str]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows to {path}")


def table_intact(dataset: str, out: str, include_all: bool) -> None:
    root = Path(dataset)
    folder = root / "table_intact"
    if not folder.exists():
        sys.exit(f"{folder} not found")
    rows = []
    for f in sorted(folder.iterdir()):
        if f.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        m = SUSPECT_TOKENS.search(f.stem)
        if m or include_all:
            rows.append(
                {
                    "rel_path": f.relative_to(root).as_posix(),
                    "reason": f"filename contains {m.group(0)!r}" if m else "full review",
                    "current_label": "intact",
                    "new_label": "",
                    "note": "",
                }
            )
    _write_csv(out, rows, REVIEW_FIELDS)


def conflicts(manifest_path: str) -> None:
    from .splits import load_manifest

    m = load_manifest(manifest_path)
    c = m["meta"]["label_conflicts"]
    if not c:
        print("no label conflicts")
        return
    for gid, members in sorted(c.items()):
        print(gid)
        for line in members:
            print(f"  {line}")


def confident_wrong(
    dataset: str, manifest_path: str, checkpoint: str, out: str, min_conf: float
) -> None:
    import torch

    from .model import load_finetuned
    from .splits import load_manifest
    from PIL import Image

    model, processor = load_finetuned(checkpoint)
    model.eval()
    m = load_manifest(manifest_path)
    root = Path(dataset)
    rows = []
    with torch.no_grad():
        for e in m["entries"]:
            if e["synthetic"]:
                continue
            img = Image.open(root / e["rel_path"]).convert("RGB")
            logits = model(**processor(images=img, return_tensors="pt")).logits
            probs = torch.softmax(logits, dim=-1)[0]
            conf, idx = probs.max(dim=-1)
            pred = ID2LABEL[int(idx)]
            if pred != e["label"] and float(conf) >= min_conf:
                rows.append(
                    {
                        "rel_path": e["rel_path"],
                        "reason": f"model says {pred} ({float(conf):.2f}) in split {e['split']}",
                        "current_label": e["label"],
                        "new_label": "",
                        "note": "",
                    }
                )
    print(
        "note: items in the train split were fit by the model, so disagreement "
        "there is stronger evidence of a bad label than on val/test."
    )
    _write_csv(out, rows, REVIEW_FIELDS)


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("table-intact")
    a.add_argument("--dataset", required=True)
    a.add_argument("--out", default="table_intact_review.csv")
    a.add_argument("--all", action="store_true", help="list every file, not just name hits")

    b = sub.add_parser("conflicts")
    b.add_argument("--manifest", required=True)

    c = sub.add_parser("confident-wrong")
    c.add_argument("--dataset", required=True)
    c.add_argument("--manifest", required=True)
    c.add_argument("--checkpoint", required=True)
    c.add_argument("--out", default="confident_wrong.csv")
    c.add_argument("--min-conf", type=float, default=0.9)

    args = ap.parse_args()
    if args.cmd == "table-intact":
        table_intact(args.dataset, args.out, args.all)
    elif args.cmd == "conflicts":
        conflicts(args.manifest)
    else:
        confident_wrong(args.dataset, args.manifest, args.checkpoint, args.out, args.min_conf)


if __name__ == "__main__":
    main()
