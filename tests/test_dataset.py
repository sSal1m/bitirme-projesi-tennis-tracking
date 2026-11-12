import json

import cv2
import numpy as np
import pytest

from scripts.train_detector import validate_dataset
from tennis_tracking.labeler import LabelWindow


def test_labeler_saves_real_coco_boxes(qapp, tmp_path):
    image = np.zeros((100, 200, 3), dtype=np.uint8)
    cv2.imencode(".jpg", image)[1].tofile(tmp_path / "clip_0001.jpg")
    window = LabelWindow(tmp_path)
    window.canvas.boxes = [{"category_id": 0, "xyxy": [0.1, 0.2, 0.2, 0.4]}]
    window.save_current()
    doc = json.loads((tmp_path / "_annotations.coco.json").read_text())
    assert doc["annotations"][0]["bbox"] == pytest.approx([20, 20, 20, 20])
    assert doc["annotations"][0]["category_id"] == 0
    window.close()


def test_dataset_rejects_same_clip_in_multiple_splits(tmp_path):
    for split in ("train", "valid", "test"):
        folder = tmp_path / split
        folder.mkdir()
        (folder / "sameclip_00001.jpg").write_bytes(b"image")
        doc = {
            "categories": [{"id": 0, "name": "ball"}, {"id": 1, "name": "racket"}],
            "images": [{"id": 1, "file_name": "sameclip_00001.jpg"}],
            "annotations": [{"image_id": 1, "category_id": 0, "bbox": [0, 0, 10, 10]}],
        }
        (folder / "_annotations.coco.json").write_text(json.dumps(doc))
    with pytest.raises(ValueError, match="sızıntısı"):
        validate_dataset(tmp_path)
