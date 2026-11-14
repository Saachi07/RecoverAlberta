"""
One-time report on the held-out test split (inventory.md section 15, step 4).

Usage:
    python -m classifier.evaluate --dataset ../../dataset --checkpoint ./checkpoints

Prints per-class precision and recall, the confusion matrix, and calibration
error, and saves them to <checkpoint>/test_report.json.

The test set is meant to be touched once per release. If a report already
exists the script stops, because running it again after tweaking the model is
how a test set quietly turns into a second validation set. Use --force only for
a new release candidate, and say so in the commit message.
"""

import argparse
import json
import os
import sys

import torch
from torch.utils.data import DataLoader

from . import metrics
from .dataset import DamageDataset, build_splits
from .labels import ID2LABEL
from .model import load_finetuned
from .train import predict_loader

CLASS_NAMES = [ID2LABEL[i] for i in range(len(ID2LABEL))]
REPORT_NAME = "test_report.json"


def evaluate(dataset_root: str, checkpoint_dir: str, batch_size: int = 16, force: bool = False) -> dict:
    report_path = os.path.join(checkpoint_dir, REPORT_NAME)
    if os.path.exists(report_path) and not force:
        sys.exit(
            f"{report_path} already exists. The test split is for one report per release. "
            "Pass --force if this is a new release candidate."
        )

    _, _, test_samples = build_splits(dataset_root)
    if not test_samples:
        sys.exit("The test split is empty. Check the dataset path and the manifest.")

    model, processor = load_finetuned(checkpoint_dir)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device)

    loader = DataLoader(
        DamageDataset(test_samples, processor, augment=False),
        batch_size=batch_size,
        shuffle=False,
        num_workers=2,
        pin_memory=True
    )
    y_true, y_pred, probs = predict_loader(model, loader)
    report = metrics.build_report(y_true, y_pred, probs, CLASS_NAMES)
    report["checkpoint"] = os.path.abspath(checkpoint_dir)

    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    return report


def print_report(report: dict) -> None:
    import numpy as np

    print(f"\nTest set: {report['n']} images")
    print(f"accuracy {report['accuracy']:.3f}   macro-F1 {report['macro_f1']:.3f}   ECE {report['ece']:.3f}\n")
    print(f"{'class':<14}{'precision':>10}{'recall':>10}{'f1':>8}{'support':>9}")
    for name, v in report["per_class"].items():
        print(f"{name:<14}{v['precision']:>10.3f}{v['recall']:>10.3f}{v['f1']:>8.3f}{v['support']:>9}")
    print("\nconfusion matrix")
    print(metrics.format_confusion(np.array(report["confusion_matrix"]), report["class_order"]))
    print(f"\nsaved to {os.path.join(report['checkpoint'], REPORT_NAME)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--checkpoint", default="./checkpoints")
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--force", action="store_true", help="overwrite an existing test report")
    args = ap.parse_args()
    print_report(evaluate(args.dataset, args.checkpoint, args.batch_size, args.force))
