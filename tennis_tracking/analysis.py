from __future__ import annotations

import json
import math
from copy import deepcopy
from pathlib import Path

import cv2
import numpy as np

from .detection import BallTracker, ColorDetector, PoseDetector, RFDETRDetector
from .domain import Calibration, Sample, Session, Shot
from .video import audio_onsets, frames, probe

_CONFIG_PATH = Path(__file__).with_name("config.json")
try:
    _CONFIG = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    MIN_BALL_SPEED = float(_CONFIG.get("min_ball_speed_normalized_per_s", 0.20))
except Exception:
    MIN_BALL_SPEED = 0.20


class AnalysisCancelled(Exception):
    pass


def classify(sample: Sample, calibration: Calibration) -> str:
    if sample.pose is None or sample.ball is None or len(sample.pose) < 17:
        return "unknown"
    left, right = sample.pose[11], sample.pose[12]
    if min(left[2], right[2]) < 0.65:
        return "unknown"
    axis = np.asarray(right[:2]) - np.asarray(left[:2])
    width = float(np.linalg.norm(axis))
    if width < 0.035:
        return "unknown"  # Side-on or occluded shoulders.
    # Anatomical right shoulder defines dominant side; works for front/back cameras.
    offset = float(np.dot(np.asarray(sample.ball) - (np.asarray(left[:2]) + right[:2]) / 2, axis)) / width
    if calibration.mirrored:
        offset = -offset
    if abs(offset) < width * 0.25:
        return "unknown"
    dominant = offset > 0 if calibration.handedness == "right" else offset < 0
    return "forehand" if dominant else "backhand"


def near_racket(sample: Sample) -> bool:
    if sample.ball is None:
        return False
    x, y = sample.ball
    if sample.racket:
        x0, y0, x1, y1 = sample.racket
        if x0 - 0.025 <= x <= x1 + 0.025 and y0 - 0.025 <= y <= y1 + 0.025:
            return True
    if sample.pose:
        for wrist in (sample.pose[15], sample.pose[16]):
            # The wrist is the handle, not the racket face. Allow for the
            # racket's reach while rejecting balls below the player's hand.
            if (
                wrist[2] > 0.6
                and abs(y - wrist[1]) < 0.16
                and np.linalg.norm(np.asarray([x, y]) - wrist[:2]) < 0.20
            ):
                return True
    return False


def detect_shots(
    samples: list[Sample], calibration: Calibration, onsets: list[float] | None = None
) -> list[Shot]:
    """Find racket-side turns, then attach a wall impact when it is visible."""
    calibration.validate()
    if len(samples) < 7:
        return []
    times = np.asarray([s.t for s in samples])
    racket_events = []
    wall_events = []
    for i, s in enumerate(samples):
        if not s.observed or s.ball is None:
            continue
        # A single-frame reversal is easily hidden by a blurred or missed ball.
        # Use observed points on both sides of a short temporal window.
        before = int(np.searchsorted(times, s.t - 0.14))
        after = int(np.searchsorted(times, s.t + 0.14))
        if before >= i or after >= len(samples) or after <= i:
            continue
        previous = next(
            (samples[j] for j in range(before, i) if samples[j].observed and samples[j].ball is not None),
            None,
        )
        following = next(
            (samples[j] for j in range(after, i, -1) if samples[j].observed and samples[j].ball is not None),
            None,
        )
        if previous is None or following is None:
            continue
        if s.t - previous.t < 0.07 or following.t - s.t < 0.07:
            continue
        v1 = np.asarray(s.ball) - previous.ball
        v2 = np.asarray(following.ball) - s.ball
        n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
        if min(n1, n2) < 0.0015:
            continue
        cosine = float(np.dot(v1, v2) / (n1 * n2))
        local_cosine = 1.0
        near_before = next(
            (
                samples[j]
                for j in range(i - 1, max(-1, i - 5), -1)
                if samples[j].observed and samples[j].ball is not None and s.t - samples[j].t >= 0.04
            ),
            None,
        )
        near_after = next(
            (
                samples[j]
                for j in range(i + 1, min(len(samples), i + 5))
                if samples[j].observed and samples[j].ball is not None and samples[j].t - s.t >= 0.04
            ),
            None,
        )
        if near_before and near_after:
            short_in = np.asarray(s.ball) - near_before.ball
            short_out = np.asarray(near_after.ball) - s.ball
            norm = np.linalg.norm(short_in) * np.linalg.norm(short_out)
            if norm > 0.000002:
                local_cosine = float(np.dot(short_in, short_out) / norm)
        downward_turn = min(s.ball[1] - previous.ball[1], s.ball[1] - following.ball[1])
        # At a wall the ball can keep moving sideways in the image. A smooth
        # vertical minimum is useful evidence even when the full 2-D vectors
        # do not reverse. Require observations right around the minimum so a
        # tracker jump after an occlusion cannot become a wall impact.
        wall_peak = 0.0
        adjacent_before = next(
            (samples[j] for j in range(i - 1, max(-1, i - 5), -1) if samples[j].observed and samples[j].ball),
            None,
        )
        adjacent_after = next(
            (
                samples[j]
                for j in range(i + 1, min(len(samples), i + 5))
                if samples[j].observed and samples[j].ball
            ),
            None,
        )
        if (
            adjacent_before
            and adjacent_after
            and s.t - adjacent_before.t <= 0.10
            and adjacent_after.t - s.t <= 0.10
        ):
            far_before = next(
                (
                    samples[j]
                    for j in range(max(0, int(np.searchsorted(times, s.t - 0.30))), i)
                    if 0.15 <= s.t - samples[j].t <= 0.30 and samples[j].observed and samples[j].ball
                ),
                None,
            )
            far_after = next(
                (
                    samples[j]
                    for j in range(min(len(samples) - 1, int(np.searchsorted(times, s.t + 0.30))), i, -1)
                    if 0.15 <= samples[j].t - s.t <= 0.30 and samples[j].observed and samples[j].ball
                ),
                None,
            )
            if far_before and far_after:
                wall_peak = min(far_before.ball[1] - s.ball[1], far_after.ball[1] - s.ball[1])
        wall = calibration.in_wall(s.reference_ball or s.ball)
        racket = near_racket(s)
        explicit_racket = s.racket is not None
        close_to_wrist = bool(
            s.pose
            and any(
                wrist[2] > 0.6
                and abs(s.ball[1] - wrist[1]) < 0.10
                and np.linalg.norm(np.asarray(s.ball) - wrist[:2]) < 0.14
                for wrist in (s.pose[15], s.pose[16])
            )
        )
        # Per-frame ball speed at the shot candidate. Rejects hand-held jitter
        # where the ball barely moves but the angle flips (cosine ≈ -1).
        ball_speed = 0.0
        if i > 0 and samples[i - 1].ball is not None and s.ball is not None:
            dt = s.t - samples[i - 1].t
            if dt > 0:
                ball_speed = float(
                    np.linalg.norm(np.asarray(s.ball) - samples[i - 1].ball)
                ) / dt
        if racket and ball_speed >= MIN_BALL_SPEED and (
            downward_turn >= 0.025
            or (cosine <= -0.45 and downward_turn >= 0.012)
            or (close_to_wrist and cosine <= -0.45)
            or (explicit_racket and cosine <= -0.15)
        ):
            kind = "racket"
        elif wall and (local_cosine <= -0.15 or (wall_peak >= 0.015 and (s.radius or 1) < 0.012)):
            # At a wall the apparent ball should not be growing through the turn.
            if (
                s.radius
                and previous.radius
                and following.radius
                and s.radius > min(previous.radius, following.radius) * 1.35
            ):
                continue
            kind = "wall"
        else:
            continue
        confidence = min(
            0.85,
            s.confidence * 0.55
            + max(0, -cosine) * 0.12
            + (0.13 if explicit_racket else 0.08 if racket else 0)
            + min(0.1, max(0, downward_turn) * 0.8)
            + 0.05 * min(n1, n2) / max(n1, n2)
            + max(0, -local_cosine) * 0.12
            + (min(0.08, max(0, wall_peak)) if kind == "wall" else 0),
        )
        timestamp = s.t
        if onsets:
            nearest = min(onsets, key=lambda t: abs(t - s.t))
            if abs(nearest - s.t) <= 0.06:
                timestamp = nearest
                confidence = min(0.9, confidence + 0.05)
        event = (timestamp, s, confidence)
        group = racket_events if kind == "racket" else wall_events
        if group and timestamp - group[-1][0] < (0.45 if racket else 0.18):
            if confidence > group[-1][2]:
                group[-1] = event
        else:
            group.append(event)
    shots = []
    for index, (contact_t, contact, contact_confidence) in enumerate(racket_events):
        next_contact = racket_events[index + 1][0] if index + 1 < len(racket_events) else math.inf
        impact = next(
            (event for event in wall_events if 0.12 < event[0] - contact_t < 1.5 and event[0] < next_contact),
            None,
        )
        shots.append(
            Shot(
                contact_t=contact_t,
                wall_t=impact[0] if impact else None,
                wall_xy=calibration.wall_point(impact[1].reference_ball or impact[1].ball)
                if impact
                else None,
                kind=classify(contact, calibration),
                confidence=min(contact_confidence, impact[2]) if impact else min(0.64, contact_confidence),
            )
        )
    return shots


class CameraMonitor:
    def __init__(self):
        self.first = None
        self.points = None
        self.motion_count = 0
        self.drift_count = 0
        self.drift = False
        self.transform = np.float32([[1, 0, 0], [0, 1, 0]])

    def reference_point(self, point: list[float] | None) -> list[float] | None:
        if point is None:
            return None
        x, y = point
        inverse = cv2.invertAffineTransform(self.transform)
        mapped = inverse @ np.asarray([x * 320, y * 180, 1], dtype=np.float32)
        return [float(mapped[0] / 320), float(mapped[1] / 180)]

    def update(self, image) -> bool:
        gray = cv2.cvtColor(cv2.resize(image, (320, 180)), cv2.COLOR_BGR2GRAY)
        if self.first is None:
            self.first = gray
            self.points = cv2.goodFeaturesToTrack(gray, maxCorners=120, qualityLevel=0.02, minDistance=12)
            return False
        if self.points is None or len(self.points) < 12:
            return False
        nxt, status, _ = cv2.calcOpticalFlowPyrLK(self.first, gray, self.points, None)
        valid = status.ravel() == 1
        if valid.sum() < 12:
            return False
        source = self.points[valid].reshape(-1, 2)
        dest = nxt[valid].reshape(-1, 2)
        transform, inliers = cv2.estimateAffinePartial2D(
            source, dest, method=cv2.RANSAC, ransacReprojThreshold=2
        )
        if transform is not None and inliers.sum() >= max(12, len(source) * 0.5):
            self.transform = transform
            displacement = np.linalg.norm(transform[:, 2])
            scale = math.hypot(transform[0, 0], transform[1, 0])
            rotation = abs(math.atan2(transform[1, 0], transform[0, 0]))
            # A few pixels of handheld drift should reduce placement certainty,
            # not erase every impact on an otherwise stable wall.
            drift = displacement > 5 or abs(scale - 1) > 0.035 or rotation > 0.025
            moved = displacement > 20 or abs(scale - 1) > 0.08 or rotation > 0.06
            self.drift_count = self.drift_count + 1 if drift else 0
            self.drift |= self.drift_count >= 3
            self.motion_count = self.motion_count + 1 if moved else 0
        return self.motion_count >= 3


def analyze(
    session: Session,
    model_path: str | None = None,
    pose_path: str | None = None,
    progress=lambda value, message: None,
    cancelled=lambda: False,
) -> Session:
    session.calibration.validate()
    info = probe(session.video_path)
    session.width, session.height, session.fps, session.duration = (
        info.width,
        info.height,
        info.fps,
        info.duration,
    )
    session.status = "analyzing"
    detector = ColorDetector() if session.detector == "color" else RFDETRDetector(model_path or "")
    pose = None
    session.warnings = []
    if session.detector == "color":
        session.warnings.append("Deneysel renk/hareket takibi: otomatik vuruş adaylarını kontrol et.")
    if pose_path and Path(pose_path).is_file():
        pose = PoseDetector(pose_path)
    else:
        session.warnings.append(
            "Vücut modeli yok; otomatik el sınıflandırması ve raket teması bulma sınırlı."
        )
    tracker, camera = BallTracker(), CameraMonitor()
    session.samples = []
    camera_moved = False
    observed = 0
    try:
        for index, t, image in frames(session.video_path, max_width=1280):
            if cancelled():
                raise AnalysisCancelled()
            balls, racket = detector.detect(image)
            sample = tracker.update(t, balls)
            sample.racket = racket
            if pose:
                sample.pose = pose.detect(image, t)
            if index % 15 == 0:
                camera_moved |= camera.update(image)
                progress(min(90, round(t / max(info.duration, 0.01) * 90)), f"Görüntü analizi · {t:.1f} sn")
            sample.reference_ball = camera.reference_point(sample.ball)
            session.samples.append(sample)
            observed += int(sample.observed)
        progress(92, "Temaslar ve ses ipuçları inceleniyor…")
        onsets = audio_onsets(session.video_path, cancelled) if info.has_audio else []
        if cancelled():
            raise AnalysisCancelled()
        session.shots = detect_shots(session.samples, session.calibration, onsets)
        if camera_moved:
            session.warnings.append("Kamera hareketi saptandı: duvar konumları ve hız tahminleri devre dışı.")
            session.calibration.fixed_contact_plane = False
            for shot in session.shots:
                shot.wall_xy = None
        elif camera.drift:
            session.warnings.append(
                "Hafif kamera kayması saptandı: hedef isabeti yaklaşık değerdir; duvar noktalarını incele."
            )
        if observed / max(1, len(session.samples)) < 0.35:
            session.warnings.append(
                "Top görünürlüğü düşük. Renk modu yerine eğitilmiş model veya elle inceleme kullan."
            )
        if not session.shots:
            session.warnings.append(
                "Otomatik vuruş adayı bulunamadı. İnceleme sekmesinden elle vuruş ekleyebilirsin."
            )
        session.automatic_shots = deepcopy(session.shots)
        session.status = "complete"
        progress(100, "Analiz hazır — otomatik adayları incele")
        return session
    finally:
        if pose:
            pose.close()
