"""Clearly synthetic showcase. These labels are NOT outputs of a trained model."""

from fractions import Fraction
from pathlib import Path

import av
import cv2
import numpy as np

from .domain import Calibration, Sample, Session, Shot


def create_demo(folder: Path) -> Session:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "synthetic-demo.mp4"
    cal = Calibration(
        wall=[[0.08, 0.12], [0.63, 0.12], [0.63, 0.66], [0.08, 0.66]], distance_m=4, fixed_contact_plane=True
    )
    session = Session(
        video_path=str(path.resolve()),
        calibration=cal,
        name="Örnek · sentetik antrenman",
        id="syntheticdemo",
        width=960,
        height=540,
        fps=30,
        duration=10,
        status="complete",
    )
    session.warnings = [
        "SENTETİK ÖRNEK: video ve etiketler arayüzü göstermek için üretildi; model doğruluk kanıtı değildir."
    ]
    wall_points = [[0.4, 0.4], [0.6, 0.5], [0.75, 0.27], [0.48, 0.6], [0.35, 0.45]]
    for i, xy in enumerate(wall_points):
        session.shots.append(
            Shot(
                contact_t=0.4 + i * 1.8,
                wall_t=0.8 + i * 1.8,
                wall_xy=xy,
                kind="backhand" if i == 3 else "forehand",
                source="manual",
                reviewed=True,
            )
        )
    write = not path.exists()
    output = av.open(str(path), "w") if write else None
    stream = output.add_stream("libx264", rate=30) if write else None
    if stream:
        stream.width, stream.height, stream.pix_fmt = 960, 540, "yuv420p"
        stream.options = {"preset": "ultrafast", "crf": "23"}
    try:
        for i in range(300):
            t = i / 30
            cycle = min(4, max(0, int((t - 0.4) / 1.8)))
            u = min(1, max(0, (t - (0.4 + cycle * 1.8)) / 0.4))
            if t > 0.8 + cycle * 1.8:
                u = max(0, 1 - (t - (0.8 + cycle * 1.8)) / 1.4)
            target = [0.08 + 0.55 * wall_points[cycle][0], 0.12 + 0.54 * wall_points[cycle][1]]
            ball = [(1 - u) * 0.76 + u * target[0], (1 - u) * 0.60 + u * target[1]]
            session.samples.append(Sample(t=t, ball=ball, radius=0.008, observed=True, confidence=1))
            if not write:
                continue
            image = np.full((540, 960, 3), (177, 178, 137), np.uint8)
            cv2.rectangle(image, (0, 340), (960, 540), (123, 146, 117), -1)
            cv2.rectangle(image, (77, 65), (605, 356), (75, 111, 55), -1)
            for x in (77, 209, 341, 473, 605):
                cv2.line(image, (x, 65), (x, 356), (93, 133, 76), 2)
            cv2.line(image, (77, 291), (605, 291), (225, 233, 210), 3)
            cv2.line(image, (0, 510), (960, 430), (225, 233, 210), 3)
            cv2.circle(image, (782, 160), 23, (71, 79, 53), -1)
            cv2.line(image, (782, 183), (780, 305), (231, 237, 221), 20)
            cv2.line(image, (780, 215), (706, 280), (231, 237, 221), 12)
            cv2.line(image, (780, 305), (733, 423), (57, 73, 51), 13)
            cv2.line(image, (780, 305), (823, 410), (57, 73, 51), 13)
            cv2.ellipse(image, (696, 294), (16, 29), 35, 0, 360, (226, 231, 212), 3)
            cv2.circle(image, (round(ball[0] * 960), round(ball[1] * 540)), 7, (73, 225, 214), -1)
            cv2.putText(
                image,
                "SYNTHETIC DEMO / NOT A MODEL RESULT",
                (24, 515),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (233, 240, 220),
                1,
                cv2.LINE_AA,
            )
            frame = av.VideoFrame.from_ndarray(image, format="bgr24")
            frame.pts, frame.time_base = i, Fraction(1, 30)
            for packet in stream.encode(frame):
                output.mux(packet)
        if stream:
            for packet in stream.encode():
                output.mux(packet)
    finally:
        if output:
            output.close()
    return session
