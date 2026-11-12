"""Split a video into fixed-length clips inside stable time ranges.

The project needs one recording per training session and short clips for
labelling. A tutorial recording often contains camera cuts; cutting only
between cuts keeps the wall calibration valid for every produced clip.

Usage:
    python scripts/split_video.py VIDEO --out-dir clips --ranges 25.2-228.7 --length 30
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import av


def parse_ranges(text: str) -> list[tuple[float, float]]:
    ranges: list[tuple[float, float]] = []
    for chunk in text.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        match = re.fullmatch(r"(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)", chunk)
        if not match:
            raise ValueError(f"Geçersiz aralık: {chunk} (örnek: 25.2-228.7)")
        start, end = float(match.group(1)), float(match.group(2))
        if end <= start:
            raise ValueError(f"Geçersiz aralık: {chunk}")
        ranges.append((start, end))
    if not ranges:
        raise ValueError("En az bir aralık verilmeli.")
    return ranges


def plan(ranges: list[tuple[float, float]], length: float) -> list[tuple[float, float]]:
    clips: list[tuple[float, float]] = []
    for start, end in ranges:
        cursor = start
        while cursor < end - 0.5:
            stop = min(cursor + length, end)
            if stop - cursor >= 1.0:
                clips.append((round(cursor, 3), round(stop, 3)))
            cursor = stop
    return clips


def write_clip(source: Path, target: Path, start: float, end: float) -> None:
    with av.open(str(source)) as container:
        video = container.streams.video[0]
        audio = container.streams.audio[0] if container.streams.audio else None
        rate = video.average_rate or 30

        with av.open(str(target), mode="w") as out:
            out_v = out.add_stream("libx264", rate=rate)
            out_v.width = video.codec_context.width
            out_v.height = video.codec_context.height
            out_v.pix_fmt = "yuv420p"
            out_v.options = {"crf": "20", "preset": "veryfast"}
            out_a = out.add_stream("aac", rate=audio.codec_context.sample_rate) if audio else None

            origin = None
            stop = False
            streams = (video, audio) if audio else (video,)
            for packet in container.demux(*streams):
                if stop:
                    break
                if packet.stream == video:
                    for frame in packet.decode():
                        timestamp = float(frame.pts * frame.time_base)
                        if origin is None:
                            origin = timestamp
                        position = timestamp - origin
                        if position < start - 0.05:
                            continue
                        if position >= end:
                            stop = True
                            break
                        # Rebase the clip so it starts at zero on its own timeline.
                        frame.pts = int(round((position - start) / frame.time_base))
                        for encoded in out_v.encode(frame):
                            out.mux(encoded)
                elif out_a is not None and packet.stream == audio:
                    for frame in packet.decode():
                        timestamp = float(frame.pts * frame.time_base)
                        position = timestamp - (origin or 0.0)
                        if position < start - 0.05 or position >= end:
                            continue
                        frame.pts = int(round((position - start) / frame.time_base))
                        for encoded in out_a.encode(frame):
                            out.mux(encoded)

            for encoded in out_v.encode():
                out.mux(encoded)
            if out_a is not None:
                for encoded in out_a.encode():
                    out.mux(encoded)


def main() -> None:
    parser = argparse.ArgumentParser(description="Videoyu sabit uzunlukta kliplere böl.")
    parser.add_argument("video")
    parser.add_argument("--out-dir", default="clips")
    parser.add_argument(
        "--ranges",
        required=True,
        help="Virülü aralıklar, virgülle: 25.2-228.7,239.8-489.9",
    )
    parser.add_argument("--length", type=float, default=30.0, help="Klip uzunluğu (saniye)")
    parser.add_argument("--prefix", default="clip")
    args = parser.parse_args()

    source = Path(args.video).resolve()
    if not source.is_file():
        raise SystemExit(f"Video bulunamadı: {source}")

    ranges = parse_ranges(args.ranges)
    clips = plan(ranges, args.length)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"{len(clips)} klip üretilecek -> {out_dir}")
    for index, (start, end) in enumerate(clips, start=1):
        target = out_dir / f"{args.prefix}_{index:02d}_{int(start):04d}-{int(end):04d}.mp4"
        print(f"  [{index}/{len(clips)}] {start:.1f}s -> {end:.1f}s  {target.name}")
        write_clip(source, target, start, end)
    print("Tamamlandı.")


if __name__ == "__main__":
    main()
