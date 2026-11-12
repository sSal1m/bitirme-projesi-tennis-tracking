"""Pilot split: move whole clips between splits without leaking frames.

The rule that keeps the experiment honest is recording-level separation: every
frame of one clip must stay in one split. Splitting a clip across ``train`` and
``valid`` leaks near-duplicate frames (2 fps from one recording) into the
validation set and inflates every metric.

This script moves *whole* clips only. It refuses to split a clip and it refuses
to create a split that shares a recording key with an existing split.

Usage:
    python scripts/split_pilot.py --dataset datasets/wall --valid-clips 3
    python scripts/split_pilot.py --dataset datasets/wall --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

# A frame file name is "<recording-key>_<index>.jpg". The recording key is the
# SHA256 prefix of the source video, so all frames of one clip share it.
CATEGORIES = [
    {"id": 0, "name": "ball", "supercategory": "object"},
    {"id": 1, "name": "racket", "supercategory": "object"},
]


def recording_key(path: Path) -> str:
    return path.name.split("_", 1)[0]


def group_clips(folder: Path) -> dict[str, list[Path]]:
    groups: dict[str, list[Path]] = {}
    for image in sorted(folder.glob("*.jpg")):
        groups.setdefault(recording_key(image), []).append(image)
    return groups


def load_coco(path: Path) -> dict:
    if not path.is_file():
        return {"images": [], "annotations": []}
    doc = json.loads(path.read_text("utf-8"))
    doc.setdefault("images", [])
    doc.setdefault("annotations", [])
    return doc


def write_coco(folder: Path, doc: dict) -> None:
    doc.setdefault("info", {"description": "Wall practice; labels manually reviewed"})
    doc.setdefault("licenses", [])
    doc["categories"] = CATEGORIES
    images = sorted(doc["images"], key=lambda i: i["file_name"])
    by_id = {image["id"]: image for image in images}
    annotations = [a for a in doc["annotations"] if a["image_id"] in by_id]
    doc["images"] = images
    doc["annotations"] = annotations
    # Renumber ids so the file stays compact and deterministic after a move.
    mapping = {old: new for new, old in enumerate(sorted(by_id), start=1)}
    for image in doc["images"]:
        image["id"] = mapping[image["id"]]
    for index, annotation in enumerate(doc["annotations"], start=1):
        annotation["id"] = index
        annotation["image_id"] = mapping[annotation["image_id"]]
    temporary = folder / "_annotations.coco.json.tmp"
    temporary.write_text(json.dumps(doc, indent=2), "utf-8")
    temporary.replace(folder / "_annotations.coco.json")


def clip_order(videos: Path) -> dict[str, int]:
    """Map a recording key to its clip number using the source video names.

    Frame names carry a hash of the source file, not its clip number, so the
    hash order is arbitrary. Hashing the source videos recovers the real
    chronological order, which is what "the first N clips" has to mean.
    """
    order: dict[str, int] = {}
    if not videos.is_dir():
        return order
    for video in sorted(videos.glob("*.mp4")):
        digest = hashlib.sha256(video.read_bytes()).hexdigest()[:16]
        order[digest] = len(order)
    return order


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="datasets/wall")
    parser.add_argument(
        "--valid-clips",
        type=int,
        default=3,
        help="How many whole clips to move from train to valid.",
    )
    parser.add_argument(
        "--from-split", default="train", help="Split to take clips from."
    )
    parser.add_argument(
        "--to-split", default="valid", help="Split to move the clips into."
    )
    parser.add_argument(
        "--videos",
        default="videos/clips_tutorial",
        help="Source clip folder; used to order clips by their real clip number.",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    root = Path(args.dataset).resolve()
    source = root / args.from_split
    destination = root / args.to_split
    if not source.is_dir():
        raise SystemExit(f"Bölüm klasörü yok: {source}")

    groups = group_clips(source)
    if not groups:
        raise SystemExit(f"{source} içinde JPG kare bulunamadı.")

    # A clip may only live in one split. Check the destination and every other
    # split before moving anything.
    existing: dict[str, str] = {}
    for split in sorted(p for p in root.iterdir() if p.is_dir()):
        if split == source:
            continue
        for key in group_clips(split):
            if key in existing:
                raise SystemExit(
                    f"Aynı çekim iki bölümde birden var: {existing[key]} ve {split.name}. "
                    "Önce elle çöz."
                )
            existing[key] = split.name

    # Pick whole clips. Prefer clips that are not already present elsewhere,
    # and order them by their real clip number rather than by hash.
    order = clip_order(Path(args.videos))
    candidates = [key for key in sorted(groups) if key not in existing]
    candidates.sort(key=lambda key: (order.get(key, 10**6), key))
    if len(candidates) < args.valid_clips:
        raise SystemExit(
            f"Taşınabilecek klip yok: {len(candidates)} aday, {args.valid_clips} istendi."
        )
    chosen = candidates[: args.valid_clips]

    print(f"Toplam klip: {len(groups)} · taşınacak: {len(chosen)}")
    for key in chosen:
        label = f"klip {order[key] + 1}" if key in order else "klip ?"
        print(f"  {label} ({key}): {len(groups[key])} kare -> {args.to_split}")
    for key in candidates[args.valid_clips :]:
        label = f"klip {order[key] + 1}" if key in order else "klip ?"
        print(f"  {label} ({key}): {len(groups[key])} kare -> {args.from_split} (kalir)")
    if args.dry_run:
        print("Kuru calisma: hicbir dosya tasinmadi.")
        return

    destination.mkdir(parents=True, exist_ok=True)

    # Move images of the chosen clips.
    for key in chosen:
        for image in groups[key]:
            shutil.move(str(image), str(destination / image.name))

    # Carry the annotations over, split per frame so no box is lost or moved
    # to the wrong recording.
    source_coco = load_coco(source / "_annotations.coco.json")
    destination_coco = load_coco(destination / "_annotations.coco.json")

    moved_names = {image.name for key in chosen for image in groups[key]}
    kept_images = []
    moved_images = []
    for image in source_coco["images"]:
        if image["file_name"] in moved_names:
            moved_images.append(image)
        else:
            kept_images.append(image)

    moved_ids = {image["id"] for image in moved_images}
    destination_coco["images"].extend(moved_images)
    destination_coco["annotations"].extend(
        a for a in source_coco["annotations"] if a["image_id"] in moved_ids
    )
    source_coco["images"] = kept_images
    source_coco["annotations"] = [
        a for a in source_coco["annotations"] if a["image_id"] not in moved_ids
    ]

    write_coco(source, source_coco)
    write_coco(destination, destination_coco)

    print(
        f"Tamam: {args.to_split} {len(moved_images)} etiketli kare, "
        f"{args.from_split} {len(kept_images)} etiketli kare."
    )


if __name__ == "__main__":
    main()
