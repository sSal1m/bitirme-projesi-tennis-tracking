import json
import zipfile

import cv2
import numpy as np
import pytest

from scripts.pack_pilot import pack_split
from scripts.split_pilot import clip_order, group_clips
from scripts.split_pilot import main as split_main


def write_image(path, size=(120, 160)):
    path.parent.mkdir(parents=True, exist_ok=True)
    image = np.zeros((size[0], size[1], 3), dtype=np.uint8)
    image[:] = (30, 90, 160)
    cv2.imencode(".jpg", image)[1].tofile(path)


def write_coco(folder, names, boxes=True):
    doc = {
        "info": {"description": "test"},
        "licenses": [],
        "categories": [
            {"id": 0, "name": "ball", "supercategory": "object"},
            {"id": 1, "name": "racket", "supercategory": "object"},
        ],
        "images": [
            {"id": index + 1, "file_name": name, "width": 160, "height": 120}
            for index, name in enumerate(names)
        ],
        "annotations": [
            {
                "id": index + 1,
                "image_id": index + 1,
                "category_id": 0,
                "bbox": [30.0, 50.0, 16.0, 16.0],
                "area": 256.0,
                "iscrowd": 0,
            }
            for index, _ in enumerate(names)
        ]
        if boxes
        else [],
    }
    (folder / "_annotations.coco.json").write_text(json.dumps(doc), "utf-8")


def build_split(folder, keys, per_key=3):
    for key in keys:
        for index in range(per_key):
            write_image(folder / f"{key}_{index:04d}.jpg")
    return folder


def test_split_moves_whole_clips_only(tmp_path, monkeypatch):
    dataset = tmp_path / "wall"
    train = build_split(dataset / "train", ["clipA", "clipB", "clipC"])
    write_coco(train, [f"{key}_{index:04d}.jpg" for key in ("clipA", "clipB", "clipC") for index in range(3)])

    monkeypatch.setattr(
        "sys.argv",
        ["split_pilot.py", "--dataset", str(dataset), "--valid-clips", "1", "--videos", str(tmp_path)],
    )
    split_main()

    valid = dataset / "valid"
    assert valid.is_dir()
    # The moved clip is complete: every frame of it is in valid, none in train.
    assert len(list(valid.glob("*.jpg"))) == 3
    assert not list(train.glob("clipA_*.jpg"))
    assert len(list(train.glob("*.jpg"))) == 6


def test_split_carries_annotations_to_the_new_split(tmp_path, monkeypatch):
    dataset = tmp_path / "wall"
    train = build_split(dataset / "train", ["clipA", "clipB"])
    write_coco(train, [f"{key}_{index:04d}.jpg" for key in ("clipA", "clipB") for index in range(3)])

    monkeypatch.setattr(
        "sys.argv",
        ["split_pilot.py", "--dataset", str(dataset), "--valid-clips", "1", "--videos", str(tmp_path)],
    )
    split_main()

    valid_doc = json.loads((dataset / "valid" / "_annotations.coco.json").read_text("utf-8"))
    train_doc = json.loads((dataset / "train" / "_annotations.coco.json").read_text("utf-8"))
    assert len(valid_doc["images"]) == 3
    assert len(valid_doc["annotations"]) == 3
    assert len(train_doc["images"]) == 3
    assert len(train_doc["annotations"]) == 3
    # Ids stay unique and every annotation points at an existing image.
    valid_ids = {image["id"] for image in valid_doc["images"]}
    assert len(valid_ids) == len(valid_doc["images"])
    assert all(a["image_id"] in valid_ids for a in valid_doc["annotations"])


def test_split_refuses_a_clip_shared_by_two_other_splits(tmp_path, monkeypatch):
    dataset = tmp_path / "wall"
    train = build_split(dataset / "train", ["clipA", "clipB"])
    # The same recording appears in valid and test: that is a leak in the data
    # itself, and the script must stop instead of silently picking clips.
    build_split(dataset / "valid", ["clipZ"])
    build_split(dataset / "test", ["clipZ"])
    write_coco(train, ["clipA_0000.jpg"])

    monkeypatch.setattr(
        "sys.argv",
        ["split_pilot.py", "--dataset", str(dataset), "--valid-clips", "1", "--videos", str(tmp_path)],
    )
    with pytest.raises(SystemExit, match="iki bölümde"):
        split_main()


def test_split_skips_a_clip_that_already_lives_in_another_split(tmp_path, monkeypatch):
    dataset = tmp_path / "wall"
    train = build_split(dataset / "train", ["clipA", "clipB"])
    # clipA is already in valid, so it must not be moved into valid again.
    build_split(dataset / "valid", ["clipA"])
    write_coco(train, ["clipA_0000.jpg"])

    monkeypatch.setattr(
        "sys.argv",
        ["split_pilot.py", "--dataset", str(dataset), "--valid-clips", "1", "--videos", str(tmp_path)],
    )
    split_main()

    valid = dataset / "valid"
    # 3 frames of clipA that were already there, plus the 3 frames of clipB
    # that moved in. clipA itself must not have been moved a second time.
    assert len(list(valid.glob("*.jpg"))) == 6
    assert len(list(train.glob("*.jpg"))) == 3
    assert len(list(train.glob("clipA_*.jpg"))) == 3


def test_group_clips_keys_by_recording(tmp_path):
    folder = tmp_path / "train"
    build_split(folder, ["clipA", "clipB"])
    groups = group_clips(folder)
    assert sorted(groups) == ["clipA", "clipB"]
    assert len(groups["clipA"]) == 3


def test_clip_order_uses_source_video_hashes(tmp_path):
    import hashlib

    videos = tmp_path / "clips"
    videos.mkdir()
    first = videos / "clip_01.mp4"
    second = videos / "clip_02.mp4"
    first.write_bytes(b"one")
    second.write_bytes(b"two")
    order = clip_order(videos)
    assert order[hashlib.sha256(b"one").hexdigest()[:16]] == 0
    assert order[hashlib.sha256(b"two").hexdigest()[:16]] == 1


def test_pack_split_writes_images_and_coco_at_the_archive_root(tmp_path):
    folder = tmp_path / "train"
    build_split(folder, ["clipA"])
    write_coco(folder, ["clipA_0000.jpg", "clipA_0001.jpg"])
    # An unlabelled frame must not be shipped.
    write_image(folder / "clipA_0002.jpg")

    destination = tmp_path / "train.zip"
    result = pack_split(folder, destination)

    assert result["packed"] == 2
    assert result["skipped"] == 1
    with zipfile.ZipFile(destination) as archive:
        names = archive.namelist()
    assert "_annotations.coco.json" in names
    assert not [name for name in names if "/" in name]
    assert sorted(n for n in names if n.endswith(".jpg")) == ["clipA_0000.jpg", "clipA_0001.jpg"]


def test_pack_split_without_annotations_packs_nothing(tmp_path):
    folder = tmp_path / "train"
    build_split(folder, ["clipA"])
    result = pack_split(folder, tmp_path / "train.zip")
    assert result["packed"] == 0
    assert not (tmp_path / "train.zip").exists()
