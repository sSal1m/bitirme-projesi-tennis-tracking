"""The app must start in RF-DETR mode when the bundled model exists, warn
loudly when it does not, and record which weights produced a session."""

from copy import deepcopy

from tennis_tracking.app import MainWindow
from tennis_tracking.domain import Calibration, Session
from tennis_tracking.modelinfo import (
    ROOT,
    default_model_path,
    find_default_model,
    fingerprint,
    startup_model_state,
)
from tennis_tracking.storage import SessionStore


def _bundled(root, name="wall-nano.pth"):
    models = root / "models"
    models.mkdir(parents=True, exist_ok=True)
    path = models / name
    path.write_bytes(b"fake-weights")
    return path


def test_bundled_model_is_found_when_present(tmp_path):
    model = _bundled(tmp_path)
    path, message = startup_model_state(tmp_path)
    assert path == model
    assert "wall-nano.pth" in message


def test_missing_bundled_model_is_reported(tmp_path):
    path, message = startup_model_state(tmp_path)
    assert path is None
    assert "wall-nano.pth" in message
    assert "deneysel" in message.lower()
    # The wording must stay non-categorical: the colour tracker *may* fail.
    assert "bulamayabilir" in message
    assert "sayabilir" in message


def test_default_model_path_is_relative_to_the_project_root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # a completely different working directory
    path = default_model_path()
    assert path == ROOT / "models" / "wall-nano.pth"
    assert path.is_absolute()
    assert ROOT in path.parents


def test_bundled_lookup_ignores_the_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    expected = default_model_path()
    if expected.is_file():
        assert find_default_model() == expected
    else:
        assert find_default_model() is None


def test_legacy_session_without_model_fields_still_opens(tmp_path):
    legacy = {
        "video_path": "v.mp4",
        "calibration": {
            "wall": [[0.1, 0.1], [0.6, 0.1], [0.6, 0.6], [0.1, 0.6]],
            "target": [0.3, 0.3, 0.7, 0.7],
        },
        "shots": [],
        "samples": [],
        "automatic_shots": [],
        "schema_version": 1,
    }
    session = Session.from_dict(legacy)
    assert session.model_path is None
    assert session.model_sha256 is None
    assert session.detector == "color"
    store = SessionStore(tmp_path)
    store.save(session)
    loaded = store.load(session.id)
    assert loaded.model_path is None
    assert loaded.model_sha256 is None


def test_fingerprint_is_stable_and_cache_safe(tmp_path):
    model = _bundled(tmp_path)
    first = fingerprint(model)
    assert first is not None
    assert len(first) == 64
    assert fingerprint(model) == first
    assert fingerprint(None) is None
    assert fingerprint(tmp_path / "nope.pth") is None


def test_app_starts_in_rfdetr_when_bundled_model_exists(qapp, tmp_path, monkeypatch):
    model = _bundled(tmp_path)
    monkeypatch.setattr(
        "tennis_tracking.app.startup_model_state", lambda *a, **k: (model, "yüklendi")
    )
    window = MainWindow(tmp_path)
    assert window.detector.currentIndex() == 1
    assert window.model_path == str(model)
    assert "wall-nano.pth" in window.model_label.text()
    window.close()


def test_app_falls_back_to_colour_mode_with_a_warning(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "tennis_tracking.app.startup_model_state", lambda *a, **k: (None, "wall-nano.pth yok")
    )
    window = MainWindow(tmp_path)
    assert window.detector.currentIndex() == 0
    assert window.model_path is None
    assert "yüklenmedi" in window.model_label.text()
    window.close()


def test_colour_tracker_shows_a_visible_warning_banner(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "tennis_tracking.app.startup_model_state", lambda *a, **k: (None, "wall-nano.pth yok")
    )
    window = MainWindow(tmp_path)
    window.show()
    assert window.detector_banner.isVisible()
    assert "DENEYSEL" in window.detector_banner.text()
    window.close()


def test_rfdetr_mode_hides_the_warning_banner(qapp, tmp_path, monkeypatch):
    model = _bundled(tmp_path)
    monkeypatch.setattr(
        "tennis_tracking.app.startup_model_state", lambda *a, **k: (model, "yüklendi")
    )
    window = MainWindow(tmp_path)
    window.show()
    assert not window.detector_banner.isVisible()
    window.close()


def test_setup_summary_reports_detector_model_corners_target_distance(
    qapp, tmp_path, monkeypatch
):
    model = _bundled(tmp_path)
    monkeypatch.setattr(
        "tennis_tracking.app.startup_model_state", lambda *a, **k: (model, "yüklendi")
    )
    window = MainWindow(tmp_path)
    text = window.setup_summary.text()
    assert "RF-DETR" in text
    assert "wall-nano.pth" in text
    assert "0/4 köşe" in text
    assert "Hedef" in text
    assert "Mesafe" in text
    assert "hız hesaplanmaz" in text
    window.close()


def test_analysis_is_blocked_when_wall_corners_are_missing(qapp, tmp_path, demo, monkeypatch):
    window = MainWindow(tmp_path)
    window.open_session(deepcopy(demo))
    window.canvas.points = [[0.1, 0.1], [0.6, 0.1], [0.6, 0.6]]
    errors = []
    monkeypatch.setattr(window, "error", lambda text: errors.append(text))
    window.start_analysis()
    assert errors, "eksik köşelerle analiz durdurulmalı"
    assert "3/4" in errors[0]
    window.close()


def test_analysis_session_records_detector_and_model_fingerprint(
    qapp, tmp_path, demo, monkeypatch
):
    model = _bundled(tmp_path)
    monkeypatch.setattr(
        "tennis_tracking.app.startup_model_state", lambda *a, **k: (model, "yüklendi")
    )
    window = MainWindow(tmp_path)
    window.open_session(deepcopy(demo))
    window.canvas.points = list(demo.calibration.wall)
    window.detector.setCurrentIndex(1)  # the demo session was analysed with colour
    session = window.build_analysis_session()
    assert session.detector == "rfdetr"
    assert session.model_path == str(model)
    assert session.model_sha256 == fingerprint(model)
    window.close()


def test_colour_mode_session_records_no_model(qapp, tmp_path, demo, monkeypatch):
    monkeypatch.setattr(
        "tennis_tracking.app.startup_model_state", lambda *a, **k: (None, "yok")
    )
    window = MainWindow(tmp_path)
    window.open_session(deepcopy(demo))
    window.canvas.points = list(demo.calibration.wall)
    window.detector.setCurrentIndex(0)
    session = window.build_analysis_session()
    assert session.detector == "color"
    assert session.model_path is None
    assert session.model_sha256 is None
    window.close()


def test_stored_session_keeps_detector_and_fingerprint(tmp_path):
    store = SessionStore(tmp_path)
    session = Session(
        video_path="v.mp4",
        calibration=Calibration(wall=[[0.1, 0.1], [0.6, 0.1], [0.6, 0.6], [0.1, 0.6]]),
        detector="rfdetr",
        model_path="models/wall-nano.pth",
        model_sha256="a" * 64,
    )
    store.save(session)
    loaded = store.load(session.id)
    assert loaded.detector == "rfdetr"
    assert loaded.model_path == "models/wall-nano.pth"
    assert loaded.model_sha256 == "a" * 64
    raw = (tmp_path / session.id / "session.json").read_text("utf-8")
    assert "wall-nano.pth" in raw
    assert "a" * 64 in raw
