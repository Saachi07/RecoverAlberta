"""
Label vocabulary and folder map for the damage classifier. No torch import, so
the splitting and audit tools can use it on a machine without a GPU stack.

These are the old 3-class labels, kept as a starting point. The target
vocabulary in inventory.md section 7 is multi-label damage plus ordinal
severity.
"""

LABEL2ID = {"intact": 0, "salvageable": 1, "destroyed": 2}
ID2LABEL = {v: k for k, v in LABEL2ID.items()}

# Maps each subfolder path (relative to dataset_root) to its class label.
# Adjust or extend this if more item types are added.
FOLDER_LABEL_MAP = {
    "chair_intact": "intact",
    "chair_intact_synthetic": "intact",
    "chair_damaged/damaged": "destroyed",
    "chair_damaged/damaged_synthetic": "destroyed",
    "chair_damaged/salvageable": "salvageable",
    "chair_damaged/salvageable_synthetic": "salvageable",
    # TODO: audit table_intact — a few filenames suggest misplaced damaged images
    # (python -m classifier.audit --dataset <root> lists the suspects)
    "table_intact": "intact",
    "table_damaged/damaged": "destroyed",
    "table_damaged/damaged_synthetic": "destroyed",
    "table_damaged/salvageable": "salvageable",
    "table_damaged/salvageable_synthetic": "salvageable",
}
