from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

import cv2
import numpy as np


@dataclass
class Calibration:
    # Normalized image coordinates, clockwise: TL, TR, BR, BL.
    wall: list[list[float]] = field(default_factory=list)
    target: list[float] = field(default_factory=lambda: [0.3, 0.3, 0.7, 0.7])
    distance_m: float | None = None
    fixed_contact_plane: bool = False
    handedness: str = "right"
    mirrored: bool = False

    def validate(self) -> None:
        pts = np.asarray(self.wall, dtype=np.float32)
        if pts.shape != (4, 2) or not np.isfinite(pts).all():
            raise ValueError("Duvarın dört köşesini sırayla seç: sol üst, sağ üst, sağ alt, sol alt.")
        if np.any(pts < 0) or np.any(pts > 1):
            raise ValueError("Duvar köşeleri görüntü içinde olmalı.")
        if not cv2.isContourConvex(pts) or abs(cv2.contourArea(pts)) < 0.005:
            raise ValueError("Duvar alanı çok küçük veya köşeler çapraz seçildi.")
        if len(self.target) != 4 or not all(math.isfinite(v) for v in self.target):
            raise ValueError("Hedef alanı geçersiz.")
        x0, y0, x1, y1 = self.target
        if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
            raise ValueError("Hedef alanı duvar içinde olmalı.")
        if self.distance_m is not None and not (0.2 <= self.distance_m <= 30):
            raise ValueError("Temas düzlemi–duvar mesafesi 0,2–30 metre arasında olmalı.")
        if self.handedness not in ("right", "left"):
            raise ValueError("El seçimi geçersiz.")

    def wall_point(self, point: list[float]) -> list[float]:
        self.validate()
        matrix = cv2.getPerspectiveTransform(
            np.asarray(self.wall, np.float32),
            np.asarray([[0, 0], [1, 0], [1, 1], [0, 1]], np.float32),
        )
        xy = cv2.perspectiveTransform(np.asarray([[point]], np.float32), matrix)[0, 0]
        return [float(xy[0]), float(xy[1])]

    def in_wall(self, point: list[float], margin: float = 0.0) -> bool:
        x, y = self.wall_point(point)
        return -margin <= x <= 1 + margin and -margin <= y <= 1 + margin

    def target_polygon(self) -> list[list[float]]:
        self.validate()
        x0, y0, x1, y1 = self.target
        inverse = cv2.getPerspectiveTransform(
            np.asarray([[0, 0], [1, 0], [1, 1], [0, 1]], np.float32),
            np.asarray(self.wall, np.float32),
        )
        corners = np.asarray([[[x0, y0], [x1, y0], [x1, y1], [x0, y1]]], np.float32)
        return cv2.perspectiveTransform(corners, inverse)[0].tolist()


@dataclass
class Sample:
    t: float
    ball: list[float] | None = None
    radius: float | None = None  # Normalized by frame width.
    confidence: float = 0.0
    observed: bool = False
    racket: list[float] | None = None  # normalized x0, y0, x1, y1
    pose: list[list[float]] | None = None  # x, y, visibility
    reference_ball: list[float] | None = None  # Ball mapped to the first camera frame for wall placement.


@dataclass
class Shot:
    contact_t: float
    wall_t: float | None = None
    wall_xy: list[float] | None = None
    kind: str = "unknown"
    confidence: float = 0.0
    source: str = "automatic"
    reviewed: bool = False
    included: bool = True
    id: str = field(default_factory=lambda: uuid4().hex)


def approach_speed_candidate(shot: Shot, calibration: Calibration) -> float | None:
    if not calibration.fixed_contact_plane or not calibration.distance_m or shot.wall_t is None:
        return None
    dt = shot.wall_t - shot.contact_t
    if not math.isfinite(dt) or dt <= 0.04 or dt > 3:
        return None
    return round(3.6 * calibration.distance_m / dt, 1)


def approach_speed(shot: Shot, calibration: Calibration) -> float | None:
    candidate = approach_speed_candidate(shot, calibration)
    if candidate is None:
        return None
    # Automatic wall matches are candidates: discard weak and unusually late
    # matches, but permit a labeled estimate without requiring manual review.
    if not shot.reviewed and (shot.confidence < 0.4 or shot.wall_t - shot.contact_t > 1.5):
        return None
    return candidate


@dataclass
class Session:
    video_path: str
    calibration: Calibration
    id: str = field(default_factory=lambda: uuid4().hex)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    name: str = "Duvar antrenmanı"
    duration: float = 0.0
    fps: float = 0.0
    width: int = 0
    height: int = 0
    detector: str = "color"
    model_path: str | None = None  # Weights that produced this session.
    model_sha256: str | None = None  # Fingerprint of the weights above.
    status: str = "ready"
    warnings: list[str] = field(default_factory=list)
    samples: list[Sample] = field(default_factory=list)
    automatic_shots: list[Shot] = field(default_factory=list)
    shots: list[Shot] = field(default_factory=list)
    schema_version: int = 1

    def summary_at(self, t: float) -> dict:
        included = [shot for shot in self.shots if shot.included and shot.contact_t <= t]
        landed = [shot for shot in included if shot.wall_t is not None and shot.wall_t <= t]
        localized = [shot for shot in landed if shot.wall_xy is not None]
        x0, y0, x1, y1 = self.calibration.target
        hits = sum(x0 <= shot.wall_xy[0] <= x1 and y0 <= shot.wall_xy[1] <= y1 for shot in localized)
        speeds = [
            value
            for shot in landed
            if (value := approach_speed(shot, self.calibration)) is not None
        ]
        return {
            "strokes": len(included),
            "forehand": sum(shot.kind == "forehand" for shot in included),
            "backhand": sum(shot.kind == "backhand" for shot in included),
            "localized": len(localized),
            "hits": hits,
            "hit_rate": round(100 * hits / len(localized), 1) if localized else None,
            "approach_kmh": round(sum(speeds) / len(speeds), 1) if speeds else None,
            "speed_count": len(speeds),
        }

    def summary(self) -> dict:
        included = [s for s in self.shots if s.included]
        localized = [s for s in included if s.wall_xy is not None]
        x0, y0, x1, y1 = self.calibration.target
        hits = sum(x0 <= s.wall_xy[0] <= x1 and y0 <= s.wall_xy[1] <= y1 for s in localized)
        measured = [
            (shot.kind, value)
            for shot in included
            if (value := approach_speed(shot, self.calibration)) is not None
        ]
        speeds = [value for _, value in measured]
        forehand_speeds = [value for kind, value in measured if kind == "forehand"]
        backhand_speeds = [value for kind, value in measured if kind == "backhand"]
        contact_times = sorted(s.contact_t for s in included)
        intervals = [b - a for a, b in zip(contact_times, contact_times[1:])]
        positions = np.asarray([s.wall_xy for s in localized])
        spread = (
            float(np.sqrt(np.mean(np.sum((positions - positions.mean(axis=0)) ** 2, axis=1))))
            if len(positions) >= 2
            else None
        )
        return {
            "strokes": len(included),
            "forehand": sum(s.kind == "forehand" for s in included),
            "backhand": sum(s.kind == "backhand" for s in included),
            "unknown": sum(s.kind == "unknown" for s in included),
            "localized": len(localized),
            "unlocalized": len(included) - len(localized),
            "hits": hits,
            "hit_rate": round(100 * hits / len(localized), 1) if localized else None,
            "approach_kmh": round(sum(speeds) / len(speeds), 1) if speeds else None,
            "peak_kmh": max(speeds) if speeds else None,
            "forehand_kmh": (
                round(sum(forehand_speeds) / len(forehand_speeds), 1)
                if forehand_speeds else None
            ),
            "backhand_kmh": (
                round(sum(backhand_speeds) / len(backhand_speeds), 1)
                if backhand_speeds else None
            ),
            "reviewed": sum(s.reviewed for s in included),
            "mean_interval_s": round(sum(intervals) / len(intervals), 3) if intervals else None,
            "placement_spread": round(spread, 4) if spread is not None else None,
        }

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, obj: dict) -> Session:
        d = dict(obj)
        if d.get("schema_version") != 1:
            raise ValueError("Bu oturum sürümü desteklenmiyor.")
        d["calibration"] = Calibration(**d["calibration"])
        d["samples"] = [Sample(**s) for s in d.get("samples", [])]
        d["shots"] = [Shot(**s) for s in d.get("shots", [])]
        d["automatic_shots"] = [Shot(**s) for s in d.get("automatic_shots", [])]
        return cls(**d)
