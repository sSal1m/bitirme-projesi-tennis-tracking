from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .domain import Sample


@dataclass
class Candidate:
    xy: list[float]
    radius: float
    confidence: float


class ColorDetector:
    """Experimental moving yellow/green ball detector, not a trained tennis model."""

    def __init__(self):
        self.background = cv2.createBackgroundSubtractorMOG2(
            history=180, varThreshold=25, detectShadows=False
        )

    def detect(self, image):
        h, w = image.shape[:2]
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        color = cv2.inRange(hsv, np.array([22, 65, 75]), np.array([48, 255, 255]))
        movement = self.background.apply(image)
        mask = cv2.bitwise_and(color, movement)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        result = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if not 4 <= area <= w * h * 0.002:
                continue
            (x, y), radius = cv2.minEnclosingCircle(contour)
            if radius < 1.2 or radius > w * 0.04:
                continue
            fill = area / (np.pi * radius**2)
            if fill < 0.18:
                continue
            result.append(Candidate([x / w, y / h], radius / w, min(0.65, 0.35 + fill * 0.3)))
        return result, None


class RFDETRDetector:
    def __init__(self, model_path: str):
        path = Path(model_path).resolve()
        manifest = path.with_suffix(".json")
        if not path.is_file() or not manifest.is_file():
            raise ValueError(
                "RF-DETR için .pth modeli ve aynı adlı .json model tanımı gerekli. models/README.md"
            )
        self.meta = json.loads(manifest.read_text("utf-8"))
        if self.meta.get("architecture") != "RFDETRNano":
            raise ValueError("Bu sürüm RFDETRNano ağırlıklarını destekliyor.")
        if not {"ball", "racket"}.issubset(self.meta.get("class_ids", {})):
            raise ValueError("Model tanımında ball ve racket sınıf kimlikleri eksik.")
        if self.meta.get("sha256") and hashlib.sha256(path.read_bytes()).hexdigest() != self.meta["sha256"]:
            raise ValueError("Model dosyası ile model tanımı eşleşmiyor (SHA256).")
        try:
            from rfdetr import RFDETRNano
        except ImportError as exc:
            raise RuntimeError(
                "RF-DETR kurulu değil. .venv\\Scripts\\python -m pip install -e .[ai]"
            ) from exc
        self.model = RFDETRNano(
            pretrain_weights=str(path), device="cpu", resolution=self.meta.get("resolution", 560)
        )

    def detect(self, image):
        h, w = image.shape[:2]
        detections = self.model.predict(cv2.cvtColor(image, cv2.COLOR_BGR2RGB), threshold=0.25)
        balls, racket, racket_confidence = [], None, 0
        for box, confidence, class_id in zip(detections.xyxy, detections.confidence, detections.class_id):
            x0, y0, x1, y1 = box
            if int(class_id) == self.meta["class_ids"]["ball"]:
                balls.append(
                    Candidate(
                        [float((x0 + x1) / (2 * w)), float((y0 + y1) / (2 * h))],
                        float((x1 - x0 + y1 - y0) / (4 * w)),
                        float(confidence),
                    )
                )
            elif int(class_id) == self.meta["class_ids"]["racket"] and confidence > racket_confidence:
                racket = [float(x0 / w), float(y0 / h), float(x1 / w), float(y1 / h)]
                racket_confidence = confidence
        return balls, racket


class PoseDetector:
    def __init__(self, model_path: str):
        import mediapipe as mp

        self.mp = mp
        self.landmarker = mp.tasks.vision.PoseLandmarker.create_from_options(
            mp.tasks.vision.PoseLandmarkerOptions(
                base_options=mp.tasks.BaseOptions(model_asset_path=model_path),
                running_mode=mp.tasks.vision.RunningMode.VIDEO,
                num_poses=1,
                min_pose_detection_confidence=0.5,
                min_pose_presence_confidence=0.5,
                min_tracking_confidence=0.5,
            )
        )
        self.last_ms = -1

    def detect(self, image, t):
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        timestamp = max(self.last_ms + 1, round(t * 1000))
        self.last_ms = timestamp
        result = self.landmarker.detect_for_video(
            self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb), timestamp
        )
        if not result.pose_landmarks:
            return None
        return [[float(p.x), float(p.y), float(p.visibility)] for p in result.pose_landmarks[0]]

    def close(self):
        self.landmarker.close()


class BallTracker:
    def __init__(self):
        self.position = None
        self.velocity = np.zeros(2)
        self.last_t = None
        self.last_observed_t = None
        self.radius = None

    def update(self, t: float, candidates: list[Candidate]) -> Sample:
        dt = t - self.last_t if self.last_t is not None else 0
        if self.last_observed_t is not None and t - self.last_observed_t > 0.12:
            self.position = None
            self.velocity[:] = 0
        predicted = self.position + self.velocity * dt if self.position is not None else None
        selected = None
        if candidates:
            if predicted is None:
                selected = max(candidates, key=lambda c: c.confidence)
            else:
                selected = min(candidates, key=lambda c: np.linalg.norm(np.asarray(c.xy) - predicted))
                gate = min(0.25, max(0.055, float(np.linalg.norm(self.velocity)) * dt * 2.5))
                if np.linalg.norm(np.asarray(selected.xy) - predicted) > gate:
                    selected = None
        sample = Sample(t=t)
        if selected:
            position = np.asarray(selected.xy)
            if self.position is not None and dt > 0:
                self.velocity = 0.6 * (position - self.position) / dt + 0.4 * self.velocity
            self.position = position
            self.last_observed_t = t
            self.radius = selected.radius
            sample.ball = selected.xy
            sample.radius = selected.radius
            sample.confidence = selected.confidence
            sample.observed = True
        elif predicted is not None and np.all(predicted >= 0) and np.all(predicted <= 1):
            self.position = predicted
            sample.ball = predicted.tolist()
            sample.radius = self.radius
        else:
            self.position = None
        self.last_t = t
        return sample
