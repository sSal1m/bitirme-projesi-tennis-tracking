"""Run the full application analysis with the trained RF-DETR model.

Re-analyses an existing session's video with the RF-DETR detector while
reusing that session's calibration, so the result is directly comparable
with the stored HSV (colour/motion) run of the very same video.

The output is a new session; the reviewed reference is never overwritten.

Usage:
    python scripts/run_rfdetr_session.py data/<SESSION_ID>
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tennis_tracking.analysis import analyze
from tennis_tracking.domain import Calibration, Session

ROOT = Path(__file__).resolve().parents[1]
POSE = ROOT / "models" / "pose_landmarker_lite.task"
MODEL = ROOT / "models" / "wall-nano.pth"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("session", help="Kaynak oturum klasörü veya session.json yolu.")
    parser.add_argument("--output", default=str(ROOT / "data"), help="Oturumların yazılacağı klasör.")
    parser.add_argument("--model", default=str(MODEL))
    args = parser.parse_args()

    source = Path(args.session)
    if source.is_dir():
        source = source / "session.json"
    doc = json.loads(source.read_text("utf-8"))

    calibration = Calibration(**doc["calibration"])
    video = Path(doc["video_path"])
    if not video.is_file():
        raise SystemExit(f"Video bulunamadi: {video}")

    session = Session(
        video_path=str(video),
        calibration=calibration,
        name=f"{doc.get('name', video.stem)} · RF-DETR",
        detector="rfdetr",
    )

    print(f"Video : {video.name}")
    print(f"Model : {Path(args.model).name}")

    def progress(value: float, message: str) -> None:
        print(f"  {value:5.1f}%  {message}", flush=True)

    analyze(session, args.model, str(POSE) if POSE.is_file() else None, progress)

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    folder = output / session.id
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "session.json"
    path.write_text(
        json.dumps(session.to_dict(), ensure_ascii=False, indent=2, allow_nan=False), "utf-8"
    )
    print(f"\nOturum yazildi: {path}")
    print(f"  otomatik vurus adayi: {len(session.automatic_shots)}")
    for warning in session.warnings:
        print(f"  uyari: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
