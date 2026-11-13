import json
import zipfile
from pathlib import Path

import pytest

from scripts.compare_detectors import (
    IOU_STRICT,
    centre_inside,
    iou,
    load_reference,
    match,
)


def test_iou_of_identical_boxes_is_one():
    box = (0.1, 0.2, 0.3, 0.5)
    assert iou(box, box) == pytest.approx(1.0)


def test_iou_of_disjoint_boxes_is_zero():
    assert iou((0.0, 0.0, 0.1, 0.1), (0.5, 0.5, 0.6, 0.6)) == 0.0


def test_iou_of_half_overlap():
    # Two 0.2-wide boxes offset by 0.1 overlap by 0.1.
    value = iou((0.0, 0.0, 0.2, 0.2), (0.1, 0.0, 0.3, 0.2))
    assert value == pytest.approx(1 / 3, rel=1e-3)


def test_match_counts_true_positive_false_positive_and_false_negative():
    truths = [(0.1, 0.1, 0.3, 0.3), (0.6, 0.6, 0.8, 0.8)]
    predictions = [
        (0.1, 0.1, 0.3, 0.3),  # exact hit
        (0.5, 0.5, 0.6, 0.6),  # wrong place
    ]
    tp, fp, fn = match(predictions, truths, IOU_STRICT)
    assert (tp, fp, fn) == (1, 1, 1)


def test_match_does_not_double_count_one_truth():
    truths = [(0.1, 0.1, 0.3, 0.3)]
    predictions = [(0.1, 0.1, 0.3, 0.3), (0.11, 0.11, 0.31, 0.31)]
    tp, fp, fn = match(predictions, truths, IOU_STRICT)
    assert tp == 1
    assert fn == 0
    assert fp == 1


def test_centre_inside_uses_the_prediction_centre():
    truth = (0.4, 0.4, 0.6, 0.6)
    assert centre_inside((0.45, 0.45, 0.55, 0.55), truth)
    # Same size, but far away.
    assert not centre_inside((0.05, 0.05, 0.15, 0.15), truth)


def test_load_reference_normalises_boxes(tmp_path):
    folder = tmp_path / "valid"
    folder.mkdir()
    doc = {
        "images": [{"id": 1, "file_name": "a.jpg", "width": 200, "height": 100}],
        "annotations": [
            {
                "id": 1,
                "image_id": 1,
                "category_id": 0,
                "bbox": [20, 10, 40, 20],
                "area": 800,
                "iscrowd": 0,
            }
        ],
    }
    (folder / "_annotations.coco.json").write_text(json.dumps(doc), "utf-8")
    reference, _ = load_reference(folder)
    boxes = reference["a.jpg"][0]
    assert len(boxes) == 1
    x0, y0, x1, y1 = boxes[0]
    assert x0 == pytest.approx(0.1)
    assert y0 == pytest.approx(0.1)
    assert x1 == pytest.approx(0.3)
    assert y1 == pytest.approx(0.3)


def test_pilot_archive_matches_the_reference_layout():
    """The shipped archives must stay loadable and consistent."""
    root = Path(__file__).resolve().parents[1]
    for split, expected in (("train", 734), ("valid", 180)):
        archive_path = root / f"{split}.zip"
        if not archive_path.is_file():
            pytest.skip(f"{split}.zip not present")
        with zipfile.ZipFile(archive_path) as archive:
            names = archive.namelist()
            assert not [n for n in names if "/" in n]
            assert "_annotations.coco.json" in names
            doc = json.loads(archive.read("_annotations.coco.json"))
            assert len(doc["images"]) == expected
            assert sorted((c["id"], c["name"]) for c in doc["categories"]) == [
                (0, "ball"),
                (1, "racket"),
            ]
