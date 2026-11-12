"""Tests for the COCO box labeler: resume behaviour and dataset integrity."""

from __future__ import annotations

import json

import cv2
import numpy as np
import pytest

from tennis_tracking.labeler import LabelWindow


@pytest.fixture
def frames(tmp_path):
    folder = tmp_path / "train"
    folder.mkdir()
    for index in range(4):
        image = np.full((120, 160, 3), index * 10, dtype=np.uint8)
        cv2.imwrite(str(folder / f"video_{index:04d}.jpg"), image)
    return folder


def test_starts_at_the_first_frame_when_nothing_is_labelled(frames, qapp):
    window = LabelWindow(frames)
    assert window.index == 0
    assert window.records == {}


def test_resumes_at_the_first_unlabelled_frame(frames, qapp):
    window = LabelWindow(frames)
    window.canvas.boxes = [{"category_id": 0, "xyxy": [0.1, 0.1, 0.2, 0.2]}]
    window.save_current()
    window.index = 2
    window.save_current()

    reopened = LabelWindow(frames)
    assert len(reopened.records) == 2
    assert reopened.index == 1
    assert reopened.records["video_0000.jpg"]["boxes"][0]["category_id"] == 0


def test_negative_example_is_kept_as_an_empty_annotation(frames, qapp):
    window = LabelWindow(frames)
    window.save_current()
    doc = json.loads((frames / "_annotations.coco.json").read_text("utf-8"))
    assert len(doc["images"]) == 1
    assert doc["annotations"] == []
    assert [c["name"] for c in doc["categories"]] == ["ball", "racket"]


def test_boxes_are_written_in_pixels(frames, qapp):
    window = LabelWindow(frames)
    window.canvas.boxes = [{"category_id": 1, "xywh": None, "xyxy": [0.25, 0.5, 0.75, 1.0]}]
    window.save_current()
    doc = json.loads((frames / "_annotations.coco.json").read_text("utf-8"))
    annotation = doc["annotations"][0]
    image = doc["images"][0]
    assert annotation["category_id"] == 1
    assert annotation["bbox"] == [0.25 * image["width"], 0.5 * image["height"], 0.5 * image["width"], 0.5 * image["height"]]
    assert annotation["area"] == pytest.approx(annotation["bbox"][2] * annotation["bbox"][3])
    assert annotation["iscrowd"] == 0
