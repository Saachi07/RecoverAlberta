"""Tests for the leak-free split, manifest, audit helpers and metrics used by the
damage classifier (ml/classifier).

Only the torch-free modules are imported (splits, labels, metrics, audit), so
this runs in CI without a GPU stack. Images are generated on the fly.
"""

import random
import sys
from pathlib import Path

import pytest

ML = Path(__file__).resolve().parent.parent / "ml"
if str(ML) not in sys.path:
    sys.path.insert(0, str(ML))

pytest.importorskip("PIL")
np = pytest.importorskip("numpy")

from PIL import Image, ImageEnhance, ImageOps  # noqa: E402

from classifier import audit, metrics, splits as S  # noqa: E402
from classifier.labels import FOLDER_LABEL_MAP  # noqa: E402


# ---------------------------------------------------------------- helpers

def _source_image(seed: int, size: int = 128) -> Image.Image:
    """A blocky random picture. Different seeds give very different hashes."""
    rng = random.Random(seed)
    small = Image.new("RGB", (8, 8))
    small.putdata([(rng.randrange(256), rng.randrange(256), rng.randrange(256)) for _ in range(64)])
    return small.resize((size, size), Image.NEAREST)


def _variant(img: Image.Image) -> Image.Image:
    """What a synthetic copy looks like: mirrored, slightly brighter, smaller."""
    out = ImageOps.mirror(img)
    out = ImageEnhance.Brightness(out).enhance(1.08)
    return out.resize((96, 96), Image.LANCZOS)


def _make_dataset(root: Path, per_folder: int = 12) -> dict[str, list[str]]:
    """Originals plus a same-named synthetic copy in the sibling folder.

    Returns {original_rel_path: [synthetic_rel_path]} for assertions.
    """
    pairs: dict[str, list[str]] = {}
    seed = 0
    for folder in ("chair_intact", "chair_damaged/damaged", "chair_damaged/salvageable"):
        synth_folder = folder + "_synthetic"
        (root / folder).mkdir(parents=True, exist_ok=True)
        (root / synth_folder).mkdir(parents=True, exist_ok=True)
        for i in range(per_folder):
            seed += 1
            img = _source_image(seed)
            name = f"img_{i:02d}.jpg"
            img.save(root / folder / name)
            _variant(img).save(root / synth_folder / name)
            pairs[f"{folder}/{name}"] = [f"{synth_folder}/{name}"]
    return pairs


def _build(root: Path, seed: int = 42, **kw):
    manifest = root / "split_manifest.csv"
    recs = S.build_manifest(str(root), FOLDER_LABEL_MAP, str(manifest), seed=seed, **kw)
    return recs, manifest


# ------------------------------------------------------------------ naming

@pytest.mark.parametrize(
    "name,expected",
    [
        ("chair_01_synthetic.jpg", "chair_01"),
        ("chair_01_aug3.png", "chair_01"),
        ("chair_01 (1).jpg", "chair_01"),
        ("Chair_01_FLIP.JPG", "chair_01"),
        ("chair_01.jpg", "chair_01"),
    ],
)
def test_normalized_stem_strips_copy_markers(name, expected):
    assert S.normalized_stem(name) == expected


def test_different_numbers_stay_different_sources():
    assert S.normalized_stem("chair_1.jpg") != S.normalized_stem("chair_2.jpg")


def test_split_folder_detects_synthetic():
    assert S.split_folder("chair_damaged/damaged_synthetic") == ("chair_damaged/damaged", "synthetic")
    assert S.split_folder("chair_intact") == ("chair_intact", "original")


# ------------------------------------------------------------------ hashing

def test_hash_survives_mirror_resize_and_brightness():
    img = _source_image(7)
    assert S.hamming(S.flip_invariant_hash(img), S.flip_invariant_hash(_variant(img))) <= S.DEFAULT_HAMMING


def test_hash_separates_different_images():
    a, b = _source_image(1), _source_image(2)
    assert S.hamming(S.flip_invariant_hash(a), S.flip_invariant_hash(b)) > S.DEFAULT_HAMMING


# -------------------------------------------------------------------- split

def test_synthetic_copies_stay_with_their_original(tmp_path):
    pairs = _make_dataset(tmp_path)
    recs, _ = _build(tmp_path, val_ratio=0.2, test_ratio=0.2)
    split_of = {r.path: r.split for r in recs}
    for original, synths in pairs.items():
        for s in synths:
            assert split_of[original] == split_of[s], f"{original} and {s} were split apart"


def test_no_leaks_and_all_splits_populated(tmp_path):
    _make_dataset(tmp_path)
    recs, _ = _build(tmp_path, val_ratio=0.2, test_ratio=0.2)
    assert S.find_leaks(recs) == []
    counts = {s: sum(1 for r in recs if r.split == s) for s in S.SPLITS}
    assert all(counts[s] > 0 for s in S.SPLITS), counts
    assert counts["train"] > counts["val"] and counts["train"] > counts["test"]


def test_each_class_appears_in_every_split(tmp_path):
    _make_dataset(tmp_path)
    recs, _ = _build(tmp_path, val_ratio=0.2, test_ratio=0.2)
    for split in S.SPLITS:
        labels = {r.label for r in recs if r.split == split}
        assert labels == {"intact", "salvageable", "destroyed"}, (split, labels)


def test_renamed_flipped_copy_is_caught_by_content(tmp_path):
    """The filename gives nothing away, only the picture does."""
    _make_dataset(tmp_path)
    sneaky = _variant(_source_image(1))  # a copy of the first source image
    (tmp_path / "chair_intact").mkdir(exist_ok=True)
    sneaky.save(tmp_path / "chair_intact" / "totally_unrelated_name.jpg")
    recs, _ = _build(tmp_path, val_ratio=0.2, test_ratio=0.2)
    by_path = {r.path: r for r in recs}
    assert by_path["chair_intact/totally_unrelated_name.jpg"].group == by_path["chair_intact/img_00.jpg"].group
    assert S.find_leaks(recs) == []


def test_same_seed_gives_same_split(tmp_path):
    _make_dataset(tmp_path)
    a, _ = _build(tmp_path, seed=3, val_ratio=0.2, test_ratio=0.2)
    b, _ = _build(tmp_path, seed=3, val_ratio=0.2, test_ratio=0.2)
    assert [(r.path, r.split) for r in a] == [(r.path, r.split) for r in b]


def test_ratios_are_validated():
    with pytest.raises(ValueError):
        S.split_groups([], val_ratio=0.6, test_ratio=0.5)


def test_empty_dataset_raises(tmp_path):
    with pytest.raises(RuntimeError):
        S.build_manifest(str(tmp_path), FOLDER_LABEL_MAP, str(tmp_path / "m.csv"))


def test_unreadable_image_is_skipped_not_fatal(tmp_path):
    _make_dataset(tmp_path)
    (tmp_path / "chair_intact" / "broken.jpg").write_bytes(b"not an image")
    recs, _ = _build(tmp_path, val_ratio=0.2, test_ratio=0.2)
    assert "chair_intact/broken.jpg" not in {r.path for r in recs}


# ----------------------------------------------------------------- manifest

def test_manifest_round_trip_and_reuse(tmp_path):
    _make_dataset(tmp_path)
    recs, manifest = _build(tmp_path, val_ratio=0.2, test_ratio=0.2)
    again = S.read_manifest(str(manifest))
    key = lambda r: (r.path, r.label, r.provenance, r.group, r.split, r.phash)  # noqa: E731
    assert sorted(map(key, recs)) == sorted(map(key, again))

    # an existing manifest is reused even if the folders change afterwards,
    # so the test set cannot drift between runs
    _source_image(999).save(tmp_path / "chair_intact" / "late_addition.jpg")
    reused = S.load_records(str(tmp_path), manifest_path=str(manifest))
    assert "chair_intact/late_addition.jpg" not in {r.path for r in reused}


def test_manifest_records_provenance(tmp_path):
    _make_dataset(tmp_path)
    recs, _ = _build(tmp_path, val_ratio=0.2, test_ratio=0.2)
    assert {r.provenance for r in recs} == {"original", "synthetic"}
    assert all(r.provenance == "synthetic" for r in recs if r.path.split("/")[-2].endswith("_synthetic"))


def test_find_leaks_reports_a_hand_made_leak(tmp_path):
    _make_dataset(tmp_path)
    recs, _ = _build(tmp_path, val_ratio=0.2, test_ratio=0.2)
    victim = next(r for r in recs if r.split == "train" and r.provenance == "synthetic")
    victim.split = "test"  # move one copy away from its original
    problems = S.find_leaks(recs)
    assert problems
    assert any("spans splits" in p for p in problems)


# -------------------------------------------------------------------- audit

def test_conflicting_labels_on_the_same_picture_are_flagged(tmp_path):
    _make_dataset(tmp_path)
    # the same photo filed as intact and as destroyed
    _source_image(1).save(tmp_path / "chair_damaged" / "damaged" / "misfiled.jpg")
    recs, _ = _build(tmp_path, val_ratio=0.2, test_ratio=0.2)
    conflicts = S.label_conflicts(recs)
    assert conflicts
    paths = {m.path for _, members in conflicts for m in members}
    assert "chair_damaged/damaged/misfiled.jpg" in paths
    assert "chair_intact/img_00.jpg" in paths


def test_filename_flags_catch_damaged_names_in_intact_folder():
    recs = [
        S.Record("table_intact/burnt_leg_3.jpg", "intact", "original", "table_intact"),
        S.Record("table_intact/oak_table_1.jpg", "intact", "original", "table_intact"),
        S.Record("chair_damaged/damaged/clean_01.jpg", "destroyed", "original", "chair_damaged/damaged"),
    ]
    flagged = {r.path for r, _ in audit.filename_flags(recs)}
    assert flagged == {"table_intact/burnt_leg_3.jpg", "chair_damaged/damaged/clean_01.jpg"}


# ------------------------------------------------------------------ metrics

def test_confusion_and_per_class_report():
    y_true = [0, 0, 1, 1, 2, 2, 2]
    y_pred = [0, 1, 1, 1, 2, 2, 0]
    cm = metrics.confusion_matrix(y_true, y_pred, 3)
    assert cm.tolist() == [[1, 1, 0], [0, 2, 0], [1, 0, 2]]
    rep = metrics.per_class_report(cm, ["intact", "salvageable", "destroyed"])
    assert rep["intact"]["precision"] == pytest.approx(0.5)
    assert rep["intact"]["recall"] == pytest.approx(0.5)
    assert rep["salvageable"]["precision"] == pytest.approx(2 / 3)
    assert rep["salvageable"]["recall"] == pytest.approx(1.0)
    assert rep["destroyed"]["support"] == 3
    assert metrics.accuracy(cm) == pytest.approx(5 / 7)


def test_macro_f1_ignores_classes_with_no_examples():
    cm = np.array([[2, 0, 0], [0, 0, 0], [0, 0, 2]])
    assert metrics.macro_f1(cm, ["a", "b", "c"]) == pytest.approx(1.0)


def test_ece_is_zero_for_a_calibrated_perfect_model_and_high_for_overconfidence():
    perfect = np.array([[1.0, 0.0], [0.0, 1.0]])
    assert metrics.expected_calibration_error(perfect, [0, 1]) == pytest.approx(0.0)

    # says 99 percent, right half the time
    overconfident = np.array([[0.99, 0.01]] * 4)
    ece = metrics.expected_calibration_error(overconfident, [0, 0, 1, 1])
    assert ece == pytest.approx(0.49, abs=0.01)


def test_build_report_has_everything_the_evaluate_script_prints():
    probs = np.array([[0.8, 0.1, 0.1], [0.2, 0.7, 0.1], [0.1, 0.1, 0.8]])
    rep = metrics.build_report([0, 1, 2], [0, 1, 2], probs, ["a", "b", "c"])
    assert rep["accuracy"] == 1.0
    assert set(rep) >= {"n", "accuracy", "macro_f1", "per_class", "confusion_matrix", "class_order", "ece"}
