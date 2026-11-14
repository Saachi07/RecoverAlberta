"""
Classification metrics for the damage classifier. numpy only, so it is testable
without torch. Used by train.py (checkpoint choice on val) and evaluate.py
(the one-time test report).
"""

from __future__ import annotations

import numpy as np


def confusion_matrix(y_true, y_pred, n_classes: int) -> np.ndarray:
    """Rows are the true class, columns the predicted class."""
    cm = np.zeros((n_classes, n_classes), dtype=int)
    for t, p in zip(y_true, y_pred):
        cm[int(t), int(p)] += 1
    return cm


def per_class_report(cm: np.ndarray, names: list[str]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for i, name in enumerate(names):
        tp = cm[i, i]
        predicted = cm[:, i].sum()
        actual = cm[i, :].sum()
        precision = tp / predicted if predicted else 0.0
        recall = tp / actual if actual else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        out[name] = {
            "precision": float(precision),
            "recall": float(recall),
            "f1": float(f1),
            "support": int(actual),
        }
    return out


def macro_f1(cm: np.ndarray, names: list[str]) -> float:
    rep = per_class_report(cm, names)
    present = [v["f1"] for v in rep.values() if v["support"] > 0]
    return float(np.mean(present)) if present else 0.0


def accuracy(cm: np.ndarray) -> float:
    total = cm.sum()
    return float(np.trace(cm) / total) if total else 0.0


def expected_calibration_error(probs: np.ndarray, y_true, n_bins: int = 10) -> float:
    """Expected calibration error on the top-1 prediction.

    probs: (n, n_classes) softmax outputs. Lower is better; 0 means a model that
    says 80 percent is right 80 percent of the time.
    """
    probs = np.asarray(probs, dtype=float)
    y_true = np.asarray(y_true)
    if len(y_true) == 0:
        return 0.0
    conf = probs.max(axis=1)
    pred = probs.argmax(axis=1)
    correct = (pred == y_true).astype(float)

    edges = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        # include 1.0 in the last bin
        mask = (conf > lo) & (conf <= hi) if lo > 0 else (conf >= lo) & (conf <= hi)
        if mask.any():
            ece += mask.mean() * abs(correct[mask].mean() - conf[mask].mean())
    return float(ece)


def format_confusion(cm: np.ndarray, names: list[str]) -> str:
    width = max(len(n) for n in names + ["true \\ pred"]) + 2
    header = "true \\ pred".ljust(width) + "".join(n.rjust(width) for n in names)
    rows = [header]
    for i, n in enumerate(names):
        rows.append(n.ljust(width) + "".join(str(int(v)).rjust(width) for v in cm[i]))
    return "\n".join(rows)


def build_report(y_true, y_pred, probs, names: list[str]) -> dict:
    cm = confusion_matrix(y_true, y_pred, len(names))
    return {
        "n": int(cm.sum()),
        "accuracy": accuracy(cm),
        "macro_f1": macro_f1(cm, names),
        "per_class": per_class_report(cm, names),
        "confusion_matrix": cm.tolist(),
        "class_order": names,
        "ece": expected_calibration_error(probs, y_true),
    }
