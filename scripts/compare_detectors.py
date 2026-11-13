"""Objective RF-DETR vs HSV comparison on manually labelled frames.

The valid split has hand-drawn ball and racket boxes. Those boxes are the
reference, so both detectors are scored against the same reference on the same
frames - the comparison is fair by construction.

Two metrics are reported, because the ball is a tiny object:

* **IoU >= 0.5** - the strict, COCO-style criterion. A hand-drawn box for a
  ball that covers 0.09% of the frame is only a few pixels wide, so a small
  size difference between the drawn box and the predicted box destroys the
  ratio even when both point at the same ball.
* **centre inside the reference box** - whether the predicted centre falls
  inside the drawn box. For objects this small this is the criterion that
  actually answers "did the detector find the ball?".

The reference box sizes are printed so the numbers can be read in context.

Usage:
    python scripts/compare_detectors.py
    python scripts/compare_detectors.py --split test
"""

from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

from tennis_tracking.detection import ColorDetector, RFDETRDetector

ROOT = Path(__file__).resolve().parents[1]

NAMES = {0: "ball", 1: "racket"}
IOU_STRICT = 0.5
IOU_LENIENT = 0.3


def iou(a: tuple, b: tuple) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    union = (ax1 - ax0) * (ay1 - ay0) + (bx1 - bx0) * (by1 - by0) - inter
    return inter / union if union > 0 else 0.0


def centre_inside(pred: tuple, truth: tuple) -> bool:
    px, py = (pred[0] + pred[2]) / 2, (pred[1] + pred[3]) / 2
    cx, cy = (truth[0] + truth[2]) / 2, (truth[1] + truth[3]) / 2
    return (
        abs(px - cx) <= (truth[2] - truth[0]) / 2
        and abs(py - cy) <= (truth[3] - truth[1]) / 2
    )


def match(predictions: list[tuple], truths: list[tuple], threshold: float) -> tuple[int, int, int]:
    """Greedy highest-IoU matching -> (tp, fp, fn)."""
    pairs = []
    for pi, prediction in enumerate(predictions):
        for ti, truth in enumerate(truths):
            score = iou(prediction, truth)
            if score >= threshold:
                pairs.append((score, pi, ti))
    pairs.sort(reverse=True)
    used_p, used_t = set(), set()
    tp = 0
    for _, pi, ti in pairs:
        if pi in used_p or ti in used_t:
            continue
        used_p.add(pi)
        used_t.add(ti)
        tp += 1
    return tp, len(predictions) - tp, len(truths) - tp


def load_reference(folder: Path):
    doc = json.loads((folder / "_annotations.coco.json").read_text("utf-8"))
    sizes = {img["id"]: (img["width"], img["height"], img["file_name"]) for img in doc["images"]}
    reference: dict[str, dict[int, list[tuple]]] = defaultdict(lambda: defaultdict(list))
    for annotation in doc["annotations"]:
        w, h, name = sizes[annotation["image_id"]]
        x, y, bw, bh = annotation["bbox"]
        reference[name][annotation["category_id"]].append(
            (x / w, y / h, (x + bw) / w, (y + bh) / h)
        )
    return reference, sizes


def score(detector, frames, reference, label: str) -> dict:
    strict = {c: {"tp": 0, "fp": 0, "fn": 0} for c in (0, 1)}
    lenient = {c: {"tp": 0, "fp": 0, "fn": 0} for c in (0, 1)}
    centre = {c: {"tp": 0, "fp": 0, "fn": 0} for c in (0, 1)}
    start = time.time()

    for path in frames:
        image = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
        balls, racket = detector.detect(image)
        predictions = {0: [], 1: []}
        for ball in balls:
            x, y = ball.xy
            r = ball.radius
            predictions[0].append((x - r, y - r, x + r, y + r))
        if racket:
            predictions[1].append(tuple(racket))

        truths = reference[path.name]
        for category in (0, 1):
            got = predictions[category]
            want = truths.get(category, [])
            for metric, threshold in (("strict", IOU_STRICT), ("lenient", IOU_LENIENT)):
                tp, fp, fn = match(got, want, threshold)
                bucket = strict if metric == "strict" else lenient
                bucket[category]["tp"] += tp
                bucket[category]["fp"] += fp
                bucket[category]["fn"] += fn
            # Centre criterion, matched one-to-one by nearest centre.
            used = set()
            for prediction in got:
                best_index, best_distance = None, None
                for index, truth in enumerate(want):
                    if index in used or not centre_inside(prediction, truth):
                        continue
                    px, py = (prediction[0] + prediction[2]) / 2, (prediction[1] + prediction[3]) / 2
                    cx, cy = (truth[0] + truth[2]) / 2, (truth[1] + truth[3]) / 2
                    distance = (px - cx) ** 2 + (py - cy) ** 2
                    if best_distance is None or distance < best_distance:
                        best_index, best_distance = index, distance
                if best_index is None:
                    centre[category]["fp"] += 1
                else:
                    used.add(best_index)
                    centre[category]["tp"] += 1
            centre[category]["fn"] += len(want) - len(used)

    return {
        "strict": strict,
        "lenient": lenient,
        "centre": centre,
        "seconds": time.time() - start,
    }


def ratios(bucket: dict) -> tuple[float, float, float]:
    tp, fp, fn = bucket["tp"], bucket["fp"], bucket["fn"]
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", default="valid", help="Split to score on.")
    parser.add_argument("--dataset", default=str(ROOT / "datasets" / "wall"))
    parser.add_argument("--model", default=str(ROOT / "models" / "wall-nano.pth"))
    args = parser.parse_args()

    folder = Path(args.dataset) / args.split
    reference, _ = load_reference(folder)
    frames = sorted(p for p in folder.glob("*.jpg") if p.name in reference)
    if not frames:
        raise SystemExit(f"{folder} icinde etiketli kare yok.")

    print(f"Bolum: {args.split} | referans kare: {len(frames)}")

    # Reference box size, so the IoU numbers can be read in context.
    for category in (0, 1):
        areas = [
            (b[2] - b[0]) * (b[3] - b[1])
            for boxes in reference.values()
            for b in boxes.get(category, [])
        ]
        if areas:
            areas = np.array(sorted(areas))
            print(
                f"  referans {NAMES[category]:7} kutu alani: medyan "
                f"{areas[len(areas) // 2] * 100:.3f}% , min {areas[0] * 100:.4f}% , "
                f"max {areas[-1] * 100:.2f}%"
            )

    detectors = {
        "RF-DETR": RFDETRDetector(args.model),
        "HSV": ColorDetector(),
    }
    results = {name: score(detector, frames, reference, name) for name, detector in detectors.items()}

    print("\n" + "=" * 92)
    print("RF-DETR Nano (wall-nano)  vs  HSV taban cizgisi")
    print(f"Kare: {len(frames)} | IoU keskin esik: {IOU_STRICT} | yapisal esik: {IOU_LENIENT}")
    print("=" * 92)
    header = (
        f"{'Sinif':<7}{'Yontem':<9}"
        f"{'TP':>5}{'FP':>5}{'FN':>5}{'P':>9}{'R':>8}{'F1':>8}"
        f"{' | merkez P':>11}{'R':>8}{'F1':>8}"
    )
    print(header)
    print("-" * len(header))
    for category in (0, 1):
        for name, result in results.items():
            for metric, tag in (("strict", ""), ("centre", " | merkez")):
                bucket = result[metric][category]
                precision, recall, f1 = ratios(bucket)
                if metric == "strict":
                    print(
                        f"{NAMES[category]:<7}{name:<9}"
                        f"{bucket['tp']:>5}{bucket['fp']:>5}{bucket['fn']:>5}"
                        f"{precision * 100:>8.1f}%{recall * 100:>7.1f}%{f1 * 100:>7.1f}%"
                        f"{'':>11}",
                        end="",
                    )
                else:
                    print(f"{precision * 100:>10.1f}%{recall * 100:>7.1f}%{f1 * 100:>7.1f}%")
        print()

    print("-" * len(header))
    print("TOPLAM (iki sinif birlikte)")
    totals = {}
    for name, result in results.items():
        for metric in ("strict", "lenient", "centre"):
            tp = sum(result[metric][c]["tp"] for c in (0, 1))
            fp = sum(result[metric][c]["fp"] for c in (0, 1))
            fn = sum(result[metric][c]["fn"] for c in (0, 1))
            precision, recall, f1 = ratios({"tp": tp, "fp": fp, "fn": fn})
            totals[(name, metric)] = {
                "tp": tp, "fp": fp, "fn": fn,
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "f1": round(f1, 4),
            }
        s = totals[(name, "strict")]
        c = totals[(name, "centre")]
        print(
            f"  {name:<9} IoU0.5: P={s['precision']*100:5.1f}% R={s['recall']*100:5.1f}% F1={s['f1']*100:5.1f}%"
            f"   |  merkez: P={c['precision']*100:5.1f}% R={c['recall']*100:5.1f}% F1={c['f1']*100:5.1f}%"
            f"   |  {results[name]['seconds']:.0f}s"
        )

    output = {
        "split": args.split,
        "frames": len(frames),
        "iou_strict": IOU_STRICT,
        "iou_lenient": IOU_LENIENT,
        "reference": "manuel etiketlenmis COCO kutulari",
        "model": Path(args.model).name,
        "detectors": {
            name: {
                "iou_strict": {
                    NAMES[c]: {
                        "tp": result["strict"][c]["tp"],
                        "fp": result["strict"][c]["fp"],
                        "fn": result["strict"][c]["fn"],
                        **dict(
                            zip(("precision", "recall", "f1"), ratios(result["strict"][c]))
                        ),
                    }
                    for c in (0, 1)
                },
                "centre_inside": {
                    NAMES[c]: {
                        "tp": result["centre"][c]["tp"],
                        "fp": result["centre"][c]["fp"],
                        "fn": result["centre"][c]["fn"],
                        **dict(
                            zip(("precision", "recall", "f1"), ratios(result["centre"][c]))
                        ),
                    }
                    for c in (0, 1)
                },
                "total_iou_strict": totals[(name, "strict")],
                "total_centre": totals[(name, "centre")],
                "seconds": round(result["seconds"], 1),
            }
            for name, result in results.items()
        },
        "note": (
            "Bu tablo yalnizca top/raket KUTUSU tespitini olcer ve valid bolumunu "
            "kullanir (modelin gormedigi egitim bolumu degil, ama train ile ayni kayittan). "
            "Vurus F1'i elle incelenmis vurus referansi gerektirir: scripts/evaluate.py."
        ),
    }
    path = ROOT / "data" / "rfdetr_vs_hsv.json"
    path.write_text(json.dumps(output, indent=2, ensure_ascii=False), "utf-8")
    print(f"\nRapor yazildi: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
