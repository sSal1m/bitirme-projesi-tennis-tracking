from __future__ import annotations

from bisect import bisect_left
from fractions import Fraction
from pathlib import Path

import av
import cv2
import numpy as np

from .analysis import AnalysisCancelled
from .domain import Session
from .video import frames

POSE_EDGES = [
    (11, 12),
    (11, 13),
    (13, 15),
    (12, 14),
    (14, 16),
    (11, 23),
    (12, 24),
    (23, 24),
    (23, 25),
    (25, 27),
    (24, 26),
    (26, 28),
]


class Overlay:
    def __init__(self, session: Session):
        self.session = session
        self.times = [s.t for s in session.samples]

    def draw(self, frame: np.ndarray, t: float) -> np.ndarray:
        out = frame.copy()
        h, w = out.shape[:2]

        def px(p):
            return round(p[0] * w), round(p[1] * h)

        cal = self.session.calibration
        if len(cal.wall) == 4:
            cv2.polylines(out, [np.asarray([px(p) for p in cal.wall])], True, (175, 220, 130), 2)
            target = np.asarray([px(p) for p in cal.target_polygon()], dtype=np.int32)
            cv2.polylines(out, [target], True, (150, 230, 190), 2)
        i = bisect_left(self.times, t)
        if self.times:
            i = min(i, len(self.times) - 1)
            sample = self.session.samples[i]
            if abs(sample.t - t) < 0.08:
                start = bisect_left(self.times, t - 0.3)
                previous = None
                for point in self.session.samples[start : i + 1]:
                    if point.ball is not None:
                        if previous and point.observed and previous.observed:
                            cv2.line(out, px(previous.ball), px(point.ball), (90, 215, 220), 2)
                        cv2.circle(
                            out,
                            px(point.ball),
                            3,
                            (90, 215, 220) if point.observed else (160, 160, 160),
                            -1 if point.observed else 1,
                        )
                        previous = point
                    else:
                        previous = None
                if sample.pose:
                    for a, b in POSE_EDGES:
                        if min(sample.pose[a][2], sample.pose[b][2]) > 0.6:
                            cv2.line(out, px(sample.pose[a]), px(sample.pose[b]), (225, 240, 225), 2)
        if len(cal.wall) == 4:
            inverse = cv2.getPerspectiveTransform(
                np.float32([[0, 0], [1, 0], [1, 1], [0, 1]]), np.float32(cal.wall)
            )
            number = 0
            for shot in self.session.shots:
                if not shot.included:
                    continue
                number += 1
                if shot.wall_xy is None or shot.wall_t is None or shot.wall_t > t:
                    continue
                p = cv2.perspectiveTransform(np.float32([[shot.wall_xy]]), inverse)[0, 0]
                point = px(p)
                cv2.circle(out, point, 12, (235, 243, 230), -1)
                cv2.putText(
                    out,
                    str(number),
                    (point[0] - 6, point[1] + 5),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.45,
                    (50, 90, 40),
                    1,
                    cv2.LINE_AA,
                )
        return out


def export_video(session: Session, destination: str, progress=lambda n, msg: None, cancelled=lambda: False):
    dst = Path(destination)
    if dst.resolve() == Path(session.video_path).resolve():
        raise ValueError("Çıktı kaynak videonun üzerine yazılamaz.")
    temp = dst.with_name(dst.stem + ".partial.mp4")
    overlay = Overlay(session)
    try:
        with av.open(str(temp), "w") as container:
            stream = container.add_stream("libx264", rate=Fraction(session.fps or 30).limit_denominator(1001))
            stream.width = session.width + session.width % 2
            stream.height = session.height + session.height % 2
            stream.pix_fmt = "yuv420p"
            stream.time_base = Fraction(1, 90000)
            stream.codec_context.time_base = Fraction(1, 90000)
            stream.options = {"crf": "22", "preset": "fast"}
            for _, t, frame in frames(session.video_path):
                if cancelled():
                    raise AnalysisCancelled()
                out = overlay.draw(frame, t)
                counts = sum(s.included and s.contact_t <= t for s in session.shots)
                cv2.rectangle(out, (0, 0), (out.shape[1], 42), (42, 75, 30), -1)
                label = f"DUVAR TENIS | Strokes: {counts} | REVIEW REQUIRED | Estimated measurements"
                cv2.putText(
                    out, label, (14, 27), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (230, 243, 225), 1, cv2.LINE_AA
                )
                if out.shape[1] != stream.width or out.shape[0] != stream.height:
                    out = cv2.copyMakeBorder(
                        out,
                        0,
                        stream.height - out.shape[0],
                        0,
                        stream.width - out.shape[1],
                        cv2.BORDER_REPLICATE,
                    )
                vf = av.VideoFrame.from_ndarray(out, format="bgr24")
                vf.pts = round(t * 90000)
                vf.time_base = Fraction(1, 90000)
                for packet in stream.encode(vf):
                    container.mux(packet)
                progress(min(99, int(100 * t / max(session.duration, 0.01))), "İşaretlenmiş video yazılıyor…")
            for packet in stream.encode():
                container.mux(packet)
        temp.replace(dst)
        progress(100, "Video dışa aktarıldı (sessiz)")
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
