"""Pack labelled frames into Colab-ready zip archives.

Two rules make the archives usable from Colab:

* Images and ``_annotations.coco.json`` sit at the **root** of the archive, not
  in a nested folder. RF-DETR then sees exactly the Roboflow layout it expects
  after extraction into ``/content/wall/<split>/``.
* Only frames that actually carry an annotation are packed. The labeler writes
  one COCO entry per frame the user saved, so an unvisited frame is simply not
  in the file. Packing unlabelled frames would ship images the trainer never
  reads and inflate the upload.

Usage:
    python scripts/pack_pilot.py --dataset datasets/wall --output .
    python scripts/pack_pilot.py --dataset datasets/wall --splits train valid
"""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path


def labelled_images(folder: Path) -> tuple[list[str], dict]:
    annotation_file = folder / "_annotations.coco.json"
    if not annotation_file.is_file():
        return [], {}
    doc = json.loads(annotation_file.read_text("utf-8"))
    names = sorted(image["file_name"] for image in doc.get("images", []))
    return names, doc


def pack_split(folder: Path, destination: Path) -> dict:
    names, doc = labelled_images(folder)
    if not names:
        return {"split": folder.name, "packed": 0, "skipped": 0, "path": None}

    missing = [name for name in names if not (folder / name).is_file()]
    if missing:
        raise SystemExit(
            f"{folder.name}: COCO'da {len(missing)} kare eksik, ilk: {missing[0]}"
        )

    annotations = doc.get("annotations", [])
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            archive.write(folder / name, arcname=name)
        archive.writestr(
            "_annotations.coco.json",
            json.dumps(doc, ensure_ascii=False, indent=2),
        )

    total_images = len(list(folder.glob("*.jpg")))
    return {
        "split": folder.name,
        "packed": len(names),
        "skipped": total_images - len(names),
        "boxes": len(annotations),
        "path": str(destination),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="datasets/wall")
    parser.add_argument("--output", default=".", help="Folder the zip files are written to.")
    parser.add_argument(
        "--splits",
        nargs="+",
        default=["train", "valid"],
        help="Splits to pack. 'test' stays untouched until the final measurement.",
    )
    args = parser.parse_args()

    root = Path(args.dataset).resolve()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)

    for split in args.splits:
        folder = root / split
        if not folder.is_dir():
            print(f"{split}: klasör yok, atlandi.")
            continue
        destination = output / f"{split}.zip"
        result = pack_split(folder, destination)
        if result["packed"] == 0:
            print(
                f"{split}: etiketli kare yok. Once {folder} icindeki kareleri "
                "etiketle: python -m tennis_tracking.labeler " + str(folder)
            )
            continue
        size = destination.stat().st_size / 1024 / 1024
        print(
            f"{split}.zip: {result['packed']} kare, {result['boxes']} kutu, "
            f"{size:.1f} MB (etiketlenmemis {result['skipped']} kare disarida)"
        )


if __name__ == "__main__":
    main()
