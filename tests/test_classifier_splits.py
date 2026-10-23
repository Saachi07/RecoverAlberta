"""Tests for the leak-free classifier splits and held-out metrics.

No torch needed: splits.py, labels.py and metrics.py are torch-free.
"""

import csv
import sys
from collections import defaultdict
from pathlib import Path

import pytest

ML = Path(__file__).resolve().parent.parent / "ml"
if str(ML) not in sys.path:
    sys.path.insert(0, str(ML))

np = pytest.importorskip("numpy")
Image = pytest.importorskip("PIL.Image")

from classifier.metrics import (  # noqa: E402
    build_report,
    confusion_matrix,
    expected_calibration_error,
)
from classifier.splits import (  # noqa: E402
    DROPPED,
    make_splits,
    samples_for,
    source_key,
)

FOLDERS = {
    "chair_intact": "chair_intact_synthetic",
    "chair_damaged/damaged": "chair_damaged/damaged_synthetic",
    "chair_damaged/salvageable": "chair_damaged/salvageable_synthetic",
}


def _noise(seed: int) -> "np.ndarray":
    return np.random.default_rng(seed).integers(0, 256, (64, 64), dtype=np.uint8)


def _save(arr, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(arr).save(path)


@pytest.fixture
def dataset(tmp_path):
    """Per class: 20 real images, a same-name synthetic (brightened) for each,
    and a mirrored copy under an unrelated filename (hash must catch it)."""
    seed = 0
    for real_dir, syn_dir in FOLDERS.items():
        tag = real_dir.replace("/", "_")
        for i in range(20):
            seed += 1
            arr = _noise(seed)
            _save(arr, tmp_path / real_dir / f"{tag}_{i}.png")
            _save(np.clip(arr.astype(int) + 8, 0, 255).astype(np.uint8),
                  tmp_path / syn_dir / f"{tag}_{i}_synthetic_1.png")
            _save(arr[:, ::-1].copy(), tmp_path / syn_dir / f"zz_{tag}_{i}.png")
    return tmp_path


class TestSourceKey:
    @pytest.mark.parametrize(
        "stem, expected",
        [
            ("chair_12_synthetic_3", "chair_12"),
            ("chair_12_aug3_flip", "chair_12"),
            ("chair_12", "chair_12"),
            ("chair_12 (1)", "chair_12"),
            ("synergy_chair", "synergy_chair"),
            ("Chair-7-SYN", "chair-7"),
        ],
    )
    def test_key(self, stem, expected):
        assert source_key(stem) == expected


class TestSplits:
    def test_no_group_spans_splits(self, dataset):
        m = make_splits(dataset, seed=1)
        splits_by_group = defaultdict(set)
        for e in m["entries"]:
            if e["split"] != DROPPED:
                splits_by_group[e["group"]].add(e["split"])
        assert all(len(s) == 1 for s in splits_by_group.values())

    def test_val_and_test_are_real_only(self, dataset):
        m = make_splits(dataset, seed=1)
        for e in m["entries"]:
            if e["split"] in ("val", "test"):
                assert not e["synthetic"]

    def test_synthetics_follow_or_drop(self, dataset):
        m = make_splits(dataset, seed=1)
        group_split = {}
        for e in m["entries"]:
            if not e["synthetic"]:
                group_split[e["group"]] = e["split"]
        for e in m["entries"]:
            if e["synthetic"]:
                gs = group_split[e["group"]]
                assert e["split"] == (gs if gs == "train" else DROPPED)

    def test_renamed_mirror_is_grouped_by_hash(self, dataset):
        m = make_splits(dataset, seed=1)
        by_path = {e["rel_path"]: e for e in m["entries"]}
        for i in range(20):
            real = by_path[f"chair_intact/chair_intact_{i}.png"]
            mirror = by_path[f"chair_intact_synthetic/zz_chair_intact_{i}.png"]
            assert real["group"] == mirror["group"]

    def test_without_hash_renamed_mirror_leaks(self, dataset):
        # Documents why the hash pass exists.
        m = make_splits(dataset, seed=1, use_hash=False)
        by_path = {e["rel_path"]: e for e in m["entries"]}
        leaked = sum(
            by_path[f"chair_intact/chair_intact_{i}.png"]["group"]
            != by_path[f"chair_intact_synthetic/zz_chair_intact_{i}.png"]["group"]
            for i in range(20)
        )
        assert leaked == 20

    def test_all_splits_cover_all_labels(self, dataset):
        m = make_splits(dataset, seed=1)
        assert m["meta"]["warnings"] == []
        for sp in ("train", "val", "test"):
            assert set(m["meta"]["counts"][sp]) == {"intact", "salvageable", "destroyed"}

    def test_deterministic_for_seed(self, dataset):
        a = make_splits(dataset, seed=7)
        b = make_splits(dataset, seed=7)
        assert [e["split"] for e in a["entries"]] == [e["split"] for e in b["entries"]]

    def test_seed_changes_assignment(self, dataset):
        a = make_splits(dataset, seed=1)
        b = make_splits(dataset, seed=2)
        assert [e["split"] for e in a["entries"]] != [e["split"] for e in b["entries"]]

    def test_ratios_validated(self, dataset):
        with pytest.raises(ValueError):
            make_splits(dataset, val_ratio=0.6, test_ratio=0.5)

    def test_samples_for_returns_label_ids(self, dataset):
        m = make_splits(dataset, seed=1)
        train = samples_for(m, "train", dataset)
        assert train and all(isinstance(lbl, int) for _, lbl in train)

    def test_unreadable_file_does_not_crash(self, dataset):
        (dataset / "chair_intact" / "broken.png").write_bytes(b"not an image")
        m = make_splits(dataset, seed=1)
        assert m["meta"]["n_unhashable"] >= 1

    def test_label_conflict_reported(self, dataset):
        arr = _noise(999)
        _save(arr, dataset / "chair_intact" / "dup_a.png")
        _save(arr, dataset / "chair_damaged/damaged" / "dup_b.png")
        m = make_splits(dataset, seed=1)
        assert m["meta"]["label_conflicts"]
        assert any("conflict" in w or "mix labels" in w for w in m["meta"]["warnings"])


class TestOverrides:
    def _write(self, path, rows):
        with open(path, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["rel_path", "label", "note"])
            w.writerows(rows)

    def test_relabel_and_drop(self, dataset, tmp_path):
        ov = tmp_path / "ov.csv"
        self._write(ov, [
            ["chair_intact/chair_intact_0.png", "destroyed", "burnt"],
            ["chair_intact/chair_intact_1.png", "drop", "not a chair"],
        ])
        m = make_splits(dataset, seed=1, overrides_path=ov)
        by_path = {e["rel_path"]: e for e in m["entries"]}
        assert by_path["chair_intact/chair_intact_0.png"]["label"] == "destroyed"
        assert by_path["chair_intact/chair_intact_0.png"]["label_source"] == "override"
        assert "chair_intact/chair_intact_1.png" not in by_path

    def test_unknown_label_rejected(self, dataset, tmp_path):
        ov = tmp_path / "ov.csv"
        self._write(ov, [["chair_intact/chair_intact_0.png", "wet", ""]])
        with pytest.raises(ValueError):
            make_splits(dataset, seed=1, overrides_path=ov)


class TestMetrics:
    def test_confusion_and_report(self):
        probs = np.array([[0.9, 0.05, 0.05], [0.1, 0.8, 0.1], [0.2, 0.2, 0.6], [0.7, 0.2, 0.1]])
        y = np.array([0, 1, 2, 2])
        cm = confusion_matrix(y, probs.argmax(axis=1), 3)
        assert cm.tolist() == [[1, 0, 0], [0, 1, 0], [1, 0, 1]]
        r = build_report(probs, y)
        assert r["accuracy"] == 0.75
        by = {row["class"]: row for row in r["per_class"]}
        assert by["intact"]["precision"] == 0.5
        assert by["destroyed"]["recall"] == 0.5

    def test_ece_zero_when_perfectly_calibrated_and_correct(self):
        probs = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
        assert expected_calibration_error(probs, np.array([0, 1])) == 0.0

    def test_ece_flags_overconfident_errors(self):
        probs = np.array([[0.99, 0.005, 0.005]] * 4)
        assert expected_calibration_error(probs, np.array([1, 1, 1, 1])) > 0.9
