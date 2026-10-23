"""Label vocabulary and folder map for the damage classifier.

Kept free of torch so the split tooling and tests can import it anywhere.

Expected directory layout (relative to dataset_root):
    chair_intact/                        -> intact
    chair_intact_synthetic/              -> intact
    chair_damaged/damaged/               -> destroyed
    chair_damaged/damaged_synthetic/     -> destroyed
    chair_damaged/salvageable/           -> salvageable
    chair_damaged/salvageable_synthetic/ -> salvageable
    table_intact/                        -> intact (audit pending, see audit.py)
    table_damaged/...                    -> same pattern as chair_damaged
"""

LABEL2ID = {"intact": 0, "salvageable": 1, "destroyed": 2}
ID2LABEL = {v: k for k, v in LABEL2ID.items()}

# Maps each subfolder (relative to dataset_root) to its class label.
FOLDER_LABEL_MAP = {
    "chair_intact": "intact",
    "chair_intact_synthetic": "intact",
    "chair_damaged/damaged": "destroyed",
    "chair_damaged/damaged_synthetic": "destroyed",
    "chair_damaged/salvageable": "salvageable",
    "chair_damaged/salvageable_synthetic": "salvageable",
    # Audit pending: run `python -m classifier.audit table-intact`, review the
    # CSV by hand, and record fixes in label_overrides.csv (see splits.py).
    "table_intact": "intact",
    "table_damaged/damaged": "destroyed",
    "table_damaged/damaged_synthetic": "destroyed",
    "table_damaged/salvageable": "salvageable",
    "table_damaged/salvageable_synthetic": "salvageable",
}

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
