"""Locate the bundled RF-DETR model and fingerprint model weights.

The app ships with ``models/wall-nano.pth``. When it is present the app should
start in RF-DETR mode instead of the experimental colour tracker, and every
stored session should record which weights produced it.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_NAME = "wall-nano.pth"

_FINGERPRINTS: dict[str, str] = {}


def default_model_path(root: Path | None = None) -> Path:
    """Where the bundled model is expected to live."""
    base = Path(root) if root is not None else ROOT
    return base / "models" / DEFAULT_MODEL_NAME


def find_default_model(root: Path | None = None) -> Path | None:
    """The bundled model, or ``None`` when it is not installed."""
    path = default_model_path(root)
    return path if path.is_file() else None


def fingerprint(path: str | Path | None) -> str | None:
    """sha256 of a model file, cached so repeated saves stay cheap."""
    if not path:
        return None
    key = str(path)
    if key in _FINGERPRINTS:
        return _FINGERPRINTS[key]
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return None
    _FINGERPRINTS[key] = digest.hexdigest()
    return _FINGERPRINTS[key]


def startup_model_state(root: Path | None = None) -> tuple[Path | None, str]:
    """Resolve the model to start with, plus the message explaining it.

    Returns ``(path, message)``. ``path`` is ``None`` when the bundled model is
    missing, and the message then warns that the colour tracker is the only
    option left.
    """
    path = find_default_model(root)
    if path is None:
        return None, (
            f"Varsayılan RF-DETR modeli bulunamadı: models/{DEFAULT_MODEL_NAME}. "
            "Renk/hareket takibi deneyseldir ve raketi güvenilir bulamaz; "
            "güvenilir sonuç için model dosyasını elle seç."
        )
    return path, f"Varsayılan RF-DETR modeli yüklendi: {path.name}"
