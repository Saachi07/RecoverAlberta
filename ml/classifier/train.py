"""
Fine-tune ViT on the damage dataset.

Usage:
    python -m classifier.train --dataset ../../dataset --output ./checkpoints

Splits are made by source-image group (see splits.py), so synthetic copies
never straddle train and val. The best checkpoint is chosen by macro-F1 on the
val split. The test split is evaluated exactly once, after training, on that
checkpoint, and the report is written to <output>/eval_report.json. The split
manifest is written to <output>/split_manifest.json.
"""

import argparse
import json
import os

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader

from .dataset import DamageDataset, build_splits
from .metrics import build_report, macro_f1
from .model import load_finetuned, load_model

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


def train(
    dataset_root: str,
    output_dir: str,
    epochs: int = 10,
    batch_size: int = 16,
    lr: float = 2e-5,
    val_ratio: float = 0.15,
    test_ratio: float = 0.15,
    seed: int = 42,
    overrides_path: str | None = None,
    hash_threshold: int = 10,
):
    os.makedirs(output_dir, exist_ok=True)
    torch.manual_seed(seed)

    print(f"Device: {DEVICE}")
    print(f"Loading dataset from: {dataset_root}")

    model, processor = load_model()
    model.to(DEVICE)

    manifest_path = os.path.join(output_dir, "split_manifest.json")
    train_samples, val_samples, test_samples = build_splits(
        dataset_root,
        val_ratio=val_ratio,
        test_ratio=test_ratio,
        seed=seed,
        manifest_path=manifest_path,
        overrides_path=overrides_path,
        hash_threshold=hash_threshold,
    )
    print(f"Train: {len(train_samples)} | Val: {len(val_samples)} | Test: {len(test_samples)}")
    print(f"Manifest: {manifest_path}")
    if not val_samples or not test_samples:
        raise SystemExit("val or test split is empty; check split_manifest.json warnings")

    train_dataset = DamageDataset(train_samples, processor)
    val_dataset = DamageDataset(val_samples, processor)
    test_dataset = DamageDataset(test_samples, processor)

    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True, num_workers=2)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False, num_workers=2)
    test_loader = DataLoader(test_dataset, batch_size=batch_size, shuffle=False, num_workers=2)

    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    criterion = nn.CrossEntropyLoss()

    best_val_f1 = -1.0

    for epoch in range(epochs):
        model.train()
        train_loss, train_correct, train_total = 0.0, 0, 0

        for batch in train_loader:
            pixel_values = batch["pixel_values"].to(DEVICE)
            labels = batch["labels"].to(DEVICE)

            outputs = model(pixel_values=pixel_values)
            loss = criterion(outputs.logits, labels)

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            train_loss += loss.item() * len(labels)
            train_correct += (outputs.logits.argmax(dim=-1) == labels).sum().item()
            train_total += len(labels)

        scheduler.step()

        probs, y_true = _predict_all(model, val_loader)
        val_acc = float((probs.argmax(axis=1) == y_true).mean()) if len(y_true) else 0.0
        val_f1 = macro_f1(y_true, probs.argmax(axis=1), probs.shape[1])

        print(
            f"Epoch {epoch + 1}/{epochs}  "
            f"loss={train_loss / train_total:.4f}  train_acc={train_correct / train_total:.3f}  "
            f"val_acc={val_acc:.3f}  val_macro_f1={val_f1:.3f}"
        )

        if val_f1 > best_val_f1:
            best_val_f1 = val_f1
            model.save_pretrained(output_dir)
            processor.save_pretrained(output_dir)
            print(f"  saved best model (val_macro_f1={val_f1:.3f})")

    print(f"\nTraining complete. Best val macro-F1: {best_val_f1:.3f}")

    # Test split: touched once, on the checkpoint chosen by val.
    best, _ = load_finetuned(output_dir)
    best.to(DEVICE)
    probs, y_true = _predict_all(best, test_loader)
    report = build_report(probs, y_true)
    report["best_val_macro_f1"] = round(best_val_f1, 4)
    report_path = os.path.join(output_dir, "eval_report.json")
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1)
    print(f"Test accuracy={report['accuracy']}  macro_f1={report['macro_f1']}  ece={report['ece']}")
    print(f"Test report: {report_path}")
    print(f"Model saved to: {output_dir}")


def _predict_all(model: nn.Module, loader: DataLoader):
    """Softmax probabilities (N, C) and true labels (N,) as numpy arrays."""
    model.eval()
    all_probs, all_labels = [], []
    with torch.no_grad():
        for batch in loader:
            pixel_values = batch["pixel_values"].to(DEVICE)
            logits = model(pixel_values=pixel_values).logits
            all_probs.append(torch.softmax(logits, dim=-1).cpu().numpy())
            all_labels.append(batch["labels"].numpy())
    if not all_probs:
        return np.zeros((0, 3)), np.zeros((0,), dtype=int)
    return np.concatenate(all_probs), np.concatenate(all_labels)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True, help="Path to dataset root")
    parser.add_argument("--output", default="./checkpoints", help="Where to save the model")
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--lr", type=float, default=2e-5)
    parser.add_argument("--val-ratio", type=float, default=0.15)
    parser.add_argument("--test-ratio", type=float, default=0.15)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--overrides", default=None, help="CSV of audited label fixes (rel_path,label,note)")
    parser.add_argument("--hash-threshold", type=int, default=10)
    args = parser.parse_args()

    train(
        dataset_root=args.dataset,
        output_dir=args.output,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        val_ratio=args.val_ratio,
        test_ratio=args.test_ratio,
        seed=args.seed,
        overrides_path=args.overrides,
        hash_threshold=args.hash_threshold,
    )
