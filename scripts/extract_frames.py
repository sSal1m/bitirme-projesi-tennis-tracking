"""Extract sparse frames. Assign whole recording sessions to one split before labelling."""

import argparse
import hashlib
from pathlib import Path

import cv2

from tennis_tracking.video import frames


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("video")
    parser.add_argument("--dataset", default="datasets/wall")
    parser.add_argument("--split", choices=["train", "valid", "test"], required=True)
    parser.add_argument("--hz", type=float, default=2)
    args = parser.parse_args()
    if not 0 < args.hz <= 60:
        parser.error("hz must be in (0, 60]")
    source = Path(args.video).resolve()
    digest = hashlib.sha256()
    with source.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    key = digest.hexdigest()[:16]
    root = Path(args.dataset)
    for split in ("train", "valid", "test"):
        if split != args.split and list((root / split).glob(f"{key}_*.jpg")):
            raise ValueError("Aynı video başka bir bölümde mevcut. Eğitim/test sızıntısı engellendi.")
    folder = root / args.split
    folder.mkdir(parents=True, exist_ok=True)
    next_t = 0
    count = 0
    for index, t, image in frames(str(source)):
        if t + 1e-6 < next_t:
            continue
        dest = folder / f"{key}_{index:07d}.jpg"
        # imencode/tofile supports Turkish Windows paths.
        ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 95])
        if not ok:
            raise RuntimeError("Kare kaydedilemedi.")
        encoded.tofile(dest)
        count += 1
        next_t = t + 1 / args.hz
    print(f"{count} kare: {folder}")


if __name__ == "__main__":
    main()
