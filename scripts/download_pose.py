"""Download only the official Google pose model; no tennis video upload."""

import urllib.request
from hashlib import sha256
from pathlib import Path

URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
EXPECTED_SHA256 = "59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a"


def main():
    folder = Path(__file__).resolve().parents[1] / "models"
    folder.mkdir(exist_ok=True)
    path = folder / "pose_landmarker_lite.task"
    if not path.exists():
        temp = path.with_suffix(".download")
        try:
            urllib.request.urlretrieve(URL, temp)
            if temp.stat().st_size < 1_000_000:
                raise RuntimeError("İndirilen model beklenenden küçük.")
            if sha256(temp.read_bytes()).hexdigest() != EXPECTED_SHA256:
                raise RuntimeError("İndirilen model beklenen SHA256 ile eşleşmiyor.")
            temp.replace(path)
        finally:
            temp.unlink(missing_ok=True)
    digest = sha256(path.read_bytes()).hexdigest()
    if digest != EXPECTED_SHA256:
        raise RuntimeError("Yerel pose modeli beklenen SHA256 ile eşleşmiyor.")
    path.with_suffix(".sha256").write_text(digest + "\n", encoding="ascii")
    print(f"Pose modeli hazır: {path}\nSHA256: {digest}")


if __name__ == "__main__":
    main()
