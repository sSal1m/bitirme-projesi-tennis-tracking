from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import av
import cv2
import numpy as np


@dataclass
class VideoInfo:
    width: int
    height: int
    fps: float
    duration: float
    frames: int
    has_audio: bool


def oriented(frame) -> np.ndarray:
    image = frame.to_ndarray(format="bgr24")
    rotation = int(round(getattr(frame, "rotation", 0))) % 360
    if rotation == 90:
        return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
    if rotation == 180:
        return cv2.rotate(image, cv2.ROTATE_180)
    if rotation == 270:
        return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    return image


def probe(path: str) -> VideoInfo:
    if not Path(path).is_file():
        raise ValueError("Video bulunamadı. Dosya taşındıysa yeniden seç.")
    with av.open(path) as container:
        if not container.streams.video:
            raise ValueError("Dosyada video akışı bulunamadı.")
        stream = container.streams.video[0]
        first = next(container.decode(stream), None)
        if first is None:
            raise ValueError("Video boş veya çözümlenemiyor.")
        image = oriented(first)
        duration = (
            float(stream.duration * stream.time_base)
            if stream.duration
            else (container.duration / av.time_base if container.duration else 0)
        )
        fps = float(stream.average_rate or 30)
        return VideoInfo(
            image.shape[1], image.shape[0], fps, duration, stream.frames, bool(container.streams.audio)
        )


def frames(path: str, max_width: int | None = None):
    with av.open(path) as container:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        origin = None
        previous = -1.0
        for index, frame in enumerate(container.decode(stream)):
            if frame.pts is None:
                raise ValueError("Video zaman damgası eksik. Normal hızda MP4 olarak yeniden dışa aktar.")
            absolute = float(frame.pts * frame.time_base)
            if origin is None:
                origin = absolute
            t = absolute - origin
            if t <= previous:
                raise ValueError("Video zaman damgaları sıralı değil; kayıt yeniden dönüştürülmeli.")
            previous = t
            image = oriented(frame)
            if max_width and image.shape[1] > max_width:
                image = cv2.resize(image, (max_width, round(image.shape[0] * max_width / image.shape[1])))
            yield index, t, image


def frame_at(path: str, t: float) -> np.ndarray:
    # Accurate seek using stream time base, preserving variable frame rate timing.
    with av.open(path) as container:
        stream = container.streams.video[0]
        first = next(container.decode(stream))
        origin = float(first.pts * first.time_base)
        if t <= 0:
            return oriented(first)
        container.seek(int((origin + t) / stream.time_base), stream=stream, backward=True)
        last = first
        for frame in container.decode(stream):
            last = frame
            if float(frame.pts * frame.time_base) - origin >= t:
                break
        return oriented(last)


def audio_onsets(path: str, cancelled=lambda: False) -> list[float]:
    """10ms energy transients; supporting evidence, never an event classifier."""
    with av.open(path) as container:
        if not container.streams.audio:
            return []
        video_stream = container.streams.video[0]
        video_first = next(container.decode(video_stream), None)
        if video_first is None:
            return []
        origin = float(video_first.pts * video_first.time_base)
    times, values = [], []
    with av.open(path) as container:
        resampler = av.AudioResampler(format="fltp", layout="mono", rate=16000)

        def mono_frames():
            for source in container.decode(audio=0):
                yield from resampler.resample(source)
            yield from resampler.resample(None)

        for frame in mono_frames():
            if cancelled():
                return []
            if frame.pts is None:
                continue
            data = frame.to_ndarray().astype(np.float32)
            if data.ndim == 2:
                data = data.mean(axis=0)
            window = max(1, int(frame.sample_rate * 0.01))
            start = float(frame.pts * frame.time_base) - origin
            for offset in range(0, len(data), window):
                block = data[offset : offset + window]
                times.append(start + offset / frame.sample_rate)
                values.append(float(np.sqrt(np.mean(block * block))))
    if len(values) < 5:
        return []
    energy = np.asarray(values)
    threshold = max(float(np.median(energy) * 3), float(np.percentile(energy, 85)))
    peaks = []
    for i in range(1, len(energy) - 1):
        if energy[i] > threshold and energy[i] > energy[i - 1] * 1.5 and energy[i] >= energy[i + 1]:
            if not peaks or times[i] - peaks[-1] > 0.08:
                peaks.append(times[i])
    return peaks
