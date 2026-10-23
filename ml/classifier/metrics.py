"""Held-out evaluation metrics (numpy only): per-class precision and recall,
confusion matrix, macro-F1, and expected calibration error."""

from __future__ import annotations

import numpy as np

from .labels import ID2LABEL


def confusion_matrix(y_true, y_pred, n_classes: int) -> np.ndarray:
    cm = np.zeros((n_classes, n_classes), dtype=int)
    for t, p in zip(y_true, y_pred):
        cm[int(t), int(p)] += 1
    return cm


def per_class_prf(cm: np.ndarray) -> list[dict]:
    rows = []
    for i in range(cm.shape[0]):
        tp = int(cm[i, i])
        fp = int(cm[:, i].sum() - tp)
        fn = int(cm[i, :].sum() - tp)
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * p * r / (p + r) if p + r else 0.0
        rows.append(
            {
                "class": ID2LABEL.get(i, str(i)),
                "precision": round(p, 4),
                "recall": round(r, 4),
                "f1": round(f1, 4),
                "support": int(cm[i, :].sum()),
            }
        )
    return rows


def expected_calibration_error(probs: np.ndarray, y_true, n_bins: int = 10) -> float:
    """Top-label ECE: weighted gap between confidence and accuracy per bin."""
    probs = np.asarray(probs, dtype=float)
    y_true = np.asarray(y_true)
    if len(y_true) == 0:
        return 0.0
    conf = probs.max(axis=1)
    correct = (probs.argmax(axis=1) == y_true).astype(float)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (conf > lo) & (conf <= hi)
        if mask.any():
            ece += mask.mean() * abs(correct[mask].mean() - conf[mask].mean())
    return float(ece)


def macro_f1(y_true, y_pred, n_classes: int) -> float:
    rows = per_class_prf(confusion_matrix(y_true, y_pred, n_classes))
    return float(np.mean([r["f1"] for r in rows])) if rows else 0.0


def build_report(probs: np.ndarray, y_true) -> dict:
    probs = np.asarray(probs, dtype=float)
    y_true = np.asarray(y_true)
    n_classes = probs.shape[1]
    y_pred = probs.argmax(axis=1)
    cm = confusion_matrix(y_true, y_pred, n_classes)
    return {
        "n": int(len(y_true)),
        "accuracy": round(float((y_pred == y_true).mean()), 4) if len(y_true) else 0.0,
        "macro_f1": round(macro_f1(y_true, y_pred, n_classes), 4),
        "per_class": per_class_prf(cm),
        "confusion_matrix": {
            "labels": [ID2LABEL.get(i, str(i)) for i in range(n_classes)],
            "rows_are_true": cm.tolist(),
        },
        "ece": round(expected_calibration_error(probs, y_true), 4),
    }
