"""
Fine-tune ViT on the fire damage dataset.

Usage:
    python -m classifier.train --dataset ../../dataset --output ./checkpoints

The script fine-tunes the full ViT model with AdamW and a cosine LR schedule.
It saves the best checkpoint by validation macro-F1 to --output.

The test split is never read here. Once you are happy with a run, report on it
once with:
    python -m classifier.evaluate --dataset ../../dataset --checkpoint ./checkpoints
"""

import argparse
import json
import os

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader

from . import metrics
from .dataset import DamageDataset, build_splits, default_manifest_path
from .labels import ID2LABEL
from .model import load_model

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
CLASS_NAMES = [ID2LABEL[i] for i in range(len(ID2LABEL))]


def train(
    dataset_root: str,
    output_dir: str,
    epochs: int = 10,
    batch_size: int = 16,
    lr: float = 2e-5,
    val_ratio: float = 0.15,
    test_ratio: float = 0.15,
    seed: int = 42,
):
    os.makedirs(output_dir, exist_ok=True)
    torch.manual_seed(seed)
    np.random.seed(seed)

    print(f"Device: {DEVICE}")
    print(f"Loading dataset from: {dataset_root}")

    model, processor = load_model()
    model.to(DEVICE)

    train_samples, val_samples, test_samples = build_splits(
        dataset_root, val_ratio=val_ratio, test_ratio=test_ratio, seed=seed
    )
    print(f"Train: {len(train_samples)} | Val: {len(val_samples)} | Test: {len(test_samples)} (held out)")

    # augmentation on the training split only
    train_dataset = DamageDataset(train_samples, processor, augment=True)
    val_dataset = DamageDataset(val_samples, processor, augment=False)

    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True, num_workers=2, pin_memory=True)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False, num_workers=2, pin_memory=True)

    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    criterion = nn.CrossEntropyLoss()

    best_f1 = -1.0
    best = {}

    for epoch in range(epochs):
        # --- Training ---
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

        # --- Validation (checkpoint choice happens here, not on test) ---
        y_true, y_pred, probs = predict_loader(model, val_loader)
        report = metrics.build_report(y_true, y_pred, probs, CLASS_NAMES)

        avg_loss = train_loss / max(train_total, 1)
        avg_acc = train_correct / max(train_total, 1)
        print(
            f"Epoch {epoch + 1}/{epochs}  loss={avg_loss:.4f}  train_acc={avg_acc:.3f}  "
            f"val_acc={report['accuracy']:.3f}  val_macro_f1={report['macro_f1']:.3f}  "
            f"val_ece={report['ece']:.3f}"
        )

        if report["macro_f1"] > best_f1:
            best_f1 = report["macro_f1"]
            best = {"epoch": epoch + 1, "val": report}
            model.save_pretrained(output_dir)
            processor.save_pretrained(output_dir)
            print(f"  ✓ Saved best model (val_macro_f1={best_f1:.3f})")

    meta = {
        "seed": seed,
        "epochs": epochs,
        "batch_size": batch_size,
        "lr": lr,
        "manifest": default_manifest_path(dataset_root),
        "split_sizes": {"train": len(train_samples), "val": len(val_samples), "test": len(test_samples)},
        "selected_by": "val macro-F1",
        "best": best,
    }
    with open(os.path.join(output_dir, "train_meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)

    print(f"\nTraining complete. Best val macro-F1: {best_f1:.3f} (epoch {best.get('epoch')})")
    print(f"Model saved to: {output_dir}")
    print("Val numbers are for tuning only. Report on the test split once with classifier.evaluate.")


def predict_loader(model: nn.Module, loader: DataLoader):
    """Run the model over a loader. Returns (y_true, y_pred, probs) as numpy arrays."""
    model.eval()
    y_true, y_pred, probs = [], [], []
    with torch.no_grad():
        for batch in loader:
            pixel_values = batch["pixel_values"].to(DEVICE)
            logits = model(pixel_values=pixel_values).logits
            p = torch.softmax(logits, dim=-1)
            y_true.extend(batch["labels"].tolist())
            y_pred.extend(p.argmax(dim=-1).cpu().tolist())
            probs.extend(p.cpu().tolist())
    return np.array(y_true), np.array(y_pred), np.array(probs)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True, help="Path to dataset root")
    parser.add_argument("--output", default="./checkpoints", help="Where to save the model")
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--lr", type=float, default=2e-5)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    train(
        dataset_root=args.dataset,
        output_dir=args.output,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        seed=args.seed,
    )
