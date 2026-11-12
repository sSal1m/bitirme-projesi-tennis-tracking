"""Small offline COCO box annotator for ball/racket datasets."""

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QKeySequence, QPainter, QPen, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .widgets import VideoCanvas, as_qimage


class BoxCanvas(VideoCanvas):
    def __init__(self):
        super().__init__()
        self.boxes = []
        self.category = 0
        self.anchor = None
        self.end = None

    def position(self, event):
        r = self.image_rect()
        return [
            min(1, max(0, (event.position().x() - r.x()) / r.width())),
            min(1, max(0, (event.position().y() - r.y()) / r.height())),
        ]

    def mousePressEvent(self, event):
        if self.image_rect().contains(event.position()):
            self.anchor = self.position(event)
            self.end = self.anchor

    def mouseMoveEvent(self, event):
        if self.anchor is not None:
            self.end = self.position(event)
            self.update()

    def mouseReleaseEvent(self, event):
        if self.anchor is not None:
            end = self.position(event)
            x0, x1 = sorted((self.anchor[0], end[0]))
            y0, y1 = sorted((self.anchor[1], end[1]))
            if x1 - x0 > 0.001 and y1 - y0 > 0.001:
                self.boxes.append({"category_id": self.category, "xyxy": [x0, y0, x1, y1]})
        self.anchor = self.end = None
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        r = self.image_rect()
        boxes = list(self.boxes)
        if self.anchor is not None and self.end is not None:
            boxes.append({"category_id": self.category, "xyxy": [*self.anchor, *self.end]})
        for box in boxes:
            x0, y0, x1, y1 = box["xyxy"]
            painter.setPen(QPen(QColor("#dcea55" if box["category_id"] == 0 else "#74caf1"), 2))
            painter.drawRect(
                QRectF(
                    r.x() + x0 * r.width(),
                    r.y() + y0 * r.height(),
                    (x1 - x0) * r.width(),
                    (y1 - y0) * r.height(),
                )
            )
            painter.drawText(
                round(r.x() + x0 * r.width()),
                round(r.y() + y0 * r.height() - 4),
                "ball" if box["category_id"] == 0 else "racket",
            )


class LabelWindow(QMainWindow):
    def __init__(self, folder):
        super().__init__()
        self.folder = Path(folder)
        self.images = sorted(self.folder.glob("*.jpg"))
        if not self.images:
            raise ValueError("Klasörde JPG kare bulunamadı. Önce scripts/extract_frames.py kullan.")
        self.index = 0
        self.file = self.folder / "_annotations.coco.json"
        self.records = {}
        if self.file.exists():
            doc = json.loads(self.file.read_text("utf-8"))
            for image in doc["images"]:
                boxes = []
                for a in doc["annotations"]:
                    if a["image_id"] == image["id"]:
                        x, y, w, h = a["bbox"]
                        boxes.append(
                            {
                                "category_id": a["category_id"],
                                "xyxy": [
                                    x / image["width"],
                                    y / image["height"],
                                    (x + w) / image["width"],
                                    (y + h) / image["height"],
                                ],
                            }
                        )
                self.records[image["file_name"]] = {
                    "width": image["width"],
                    "height": image["height"],
                    "boxes": boxes,
                }
        self.setWindowTitle("Duvar Tenis · Veri etiketleme")
        self.resize(1180, 800)
        widget = QWidget()
        self.setCentralWidget(widget)
        layout = QVBoxLayout(widget)
        self.status = QLabel()
        layout.addWidget(self.status)
        self.canvas = BoxCanvas()
        layout.addWidget(self.canvas, 1)
        row = QHBoxLayout()
        self.category = QComboBox()
        self.category.addItems(["Top (B)", "Raket (R)"])
        self.category.currentIndexChanged.connect(lambda i: setattr(self.canvas, "category", i))
        row.addWidget(self.category)
        for text, callback in [
            ("Son kutuyu sil", self.undo),
            ("Önceki", lambda: self.advance(-1)),
            ("Kaydet ve sonraki (N)", lambda: self.advance(1)),
            ("Kaydet", self.save_current),
        ]:
            b = QPushButton(text)
            b.clicked.connect(callback)
            row.addWidget(b)
        layout.addLayout(row)
        layout.addWidget(
            QLabel(
                "Nesnenin çevresine kutu çiz. Görünmeyen topu tahmin ederek etiketleme. Kutusuz kaydetmek negatif örnek oluşturur."
            )
        )
        for key, callback in [
            ("B", lambda: self.category.setCurrentIndex(0)),
            ("R", lambda: self.category.setCurrentIndex(1)),
            ("N", lambda: self.advance(1)),
            ("Backspace", self.undo),
        ]:
            QShortcut(QKeySequence(key), self, activated=callback)
        self.load()

    def load(self):
        path = self.images[self.index]
        image = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(f"Görüntü açılamadı: {path}")
        self.canvas.set_image(as_qimage(image))
        self.canvas.boxes = list(self.records.get(path.name, {}).get("boxes", []))
        self.status.setText(
            f"{self.index + 1}/{len(self.images)} · {path.name} · {len(self.records)} kare kaydedildi"
        )
        self.canvas.update()

    def undo(self):
        if self.canvas.boxes:
            self.canvas.boxes.pop()
            self.canvas.update()

    def save_current(self):
        self.records[self.images[self.index].name] = {
            "width": self.canvas.image.width(),
            "height": self.canvas.image.height(),
            "boxes": list(self.canvas.boxes),
        }
        doc = {
            "info": {"description": "Wall practice; labels manually reviewed"},
            "licenses": [],
            "categories": [
                {"id": 0, "name": "ball", "supercategory": "object"},
                {"id": 1, "name": "racket", "supercategory": "object"},
            ],
            "images": [],
            "annotations": [],
        }
        for image_id, (name, record) in enumerate(sorted(self.records.items()), start=1):
            w, h = record["width"], record["height"]
            doc["images"].append({"id": image_id, "file_name": name, "width": w, "height": h})
            for box in record["boxes"]:
                x0, y0, x1, y1 = box["xyxy"]
                bbox = [x0 * w, y0 * h, (x1 - x0) * w, (y1 - y0) * h]
                doc["annotations"].append(
                    {
                        "id": len(doc["annotations"]) + 1,
                        "image_id": image_id,
                        "category_id": box["category_id"],
                        "bbox": bbox,
                        "area": bbox[2] * bbox[3],
                        "iscrowd": 0,
                    }
                )
        temp = self.file.with_suffix(".tmp")
        temp.write_text(json.dumps(doc, indent=2), "utf-8")
        temp.replace(self.file)
        self.status.setText(f"Kaydedildi · {len(self.records)}/{len(self.images)} kare")

    def advance(self, delta):
        self.save_current()
        self.index = min(len(self.images) - 1, max(0, self.index + delta))
        self.load()

    def closeEvent(self, event):
        self.save_current()
        event.accept()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("folder")
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    window = LabelWindow(args.folder)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
