"""Train RF-DETR Nano on a reviewed local COCO dataset, with explicit split checks."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path


def validate_dataset(root: Path):
    seen = set()
    for split in ("train", "valid", "test"):
        folder = root / split
        doc = json.loads((folder / "_annotations.coco.json").read_text("utf-8"))
        categories = sorted(doc["categories"], key=lambda c: c["id"])
        if [(c["id"], c["name"]) for c in categories] != [(0, "ball"), (1, "racket")]:
            raise ValueError("Beklenen kategoriler: 0=ball, 1=racket. Dahili etiketleyiciyi kullan.")
        if not doc["images"] or not doc["annotations"]:
            raise ValueError(f"{split} bölümü boş.")
        current = {i["file_name"].split("_")[0] for i in doc["images"]}
        if current & seen:
            raise ValueError("Aynı çekim birden fazla bölümde bulundu; veri sızıntısı var.")
        seen |= current
        ids = {image["id"] for image in doc["images"]}
        for image in doc["images"]:
            if not (folder / image["file_name"]).is_file():
                raise ValueError(f"Kare eksik: {image['file_name']}")
        for annotation in doc["annotations"]:
            if annotation["image_id"] not in ids or annotation["category_id"] not in (0, 1):
                raise ValueError("COCO anotasyon referansı geçersiz.")
            if len(annotation["bbox"]) != 4 or min(annotation["bbox"][2:]) <= 0:
                raise ValueError("COCO kutusu geçersiz.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="datasets/wall")
    parser.add_argument("--output", default="runs/wall-nano")
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    dataset = Path(args.dataset).resolve()
    validate_dataset(dataset)
    if args.check_only:
        print("COCO yapısı ve çekim bazlı bölüm ayrımı uygun.")
        return
    import torch
    from rfdetr import RFDETRNano

    if not torch.cuda.is_available():
        raise RuntimeError("Eğitim için CUDA GPU gerekli. Hazırlanan notebook'u GPU ortamında çalıştır.")
    model = RFDETRNano(resolution=560)
    model.train(
        dataset_dir=str(dataset),
        epochs=args.epochs,
        batch_size=2,
        grad_accum_steps=8,
        lr=1e-4,
        output_dir=args.output,
        resolution=560,
        device="cuda",
        early_stopping=True,
        early_stopping_patience=8,
        tensorboard=False,
        wandb=False,
    )
    output = Path(args.output)
    source = output / "checkpoint_best_total.pth"
    if not source.exists():
        raise RuntimeError("checkpoint_best_total.pth üretilmedi; eğitim günlüğünü kontrol et.")
    bundle = output / "wall-nano.pth"
    shutil.copy2(source, bundle)
    metadata = {
        "architecture": "RFDETRNano",
        "resolution": 560,
        "class_ids": {"ball": 0, "racket": 1},
        "rfdetr_version": "1.11.0",
        "sha256": hashlib.sha256(bundle.read_bytes()).hexdigest(),
        "dataset": str(dataset),
        "validation": "Saha ölçümleri evaluate.py ile ayrıca yapılmalı.",
    }
    bundle.with_suffix(".json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), "utf-8")
    print(f"Model paketi: {bundle} ve {bundle.with_suffix('.json')}")


if __name__ == "__main__":
    main()
