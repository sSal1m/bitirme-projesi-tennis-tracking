import json
from copy import deepcopy

import pytest

from tennis_tracking.domain import Calibration, Session, Shot, approach_speed, approach_speed_candidate
from tennis_tracking.hardware import display_packet
from tennis_tracking.storage import SessionStore, export_csv, export_json


def test_perspective_mapping_and_outside(calibration):
    assert calibration.wall_point([0.35, 0.4]) == pytest.approx([0.5, 0.5])
    assert calibration.in_wall([0.4, 0.3])
    assert not calibration.in_wall([0.9, 0.3])
    assert calibration.target_polygon()[0] == pytest.approx([0.25, 0.28])


@pytest.mark.parametrize(
    "wall", [[], [[0, 0]] * 4, [[0, 0], [1, 1], [1, 0], [0, 1]], [[0, 0], [1, 0], [float("nan"), 1], [0, 1]]]
)
def test_bad_geometry_rejected(wall):
    with pytest.raises(ValueError):
        Calibration(wall=wall).validate()


def test_speed_requires_measured_plane_and_reliable_timing(calibration):
    shot = Shot(1, 1.4, reviewed=True)
    assert approach_speed(shot, calibration) is None
    calibration.distance_m = 4
    assert approach_speed(shot, calibration) is None
    calibration.fixed_contact_plane = True
    assert approach_speed(shot, calibration) == 36
    shot.reviewed = False
    assert approach_speed(shot, calibration) is None
    shot.confidence = 0.8
    assert approach_speed(shot, calibration) == 36
    shot.confidence = 0.5
    assert approach_speed(shot, calibration) == 36
    shot.confidence = 0.3
    assert approach_speed(shot, calibration) is None
    shot.confidence = 0.5
    shot.wall_t = 2.6
    assert approach_speed(shot, calibration) is None
    shot.wall_t = 0.9
    assert approach_speed(shot, calibration) is None


def test_candidate_speed_and_live_summary_wait_for_wall_contact(calibration):
    calibration.distance_m = 4
    calibration.fixed_contact_plane = True
    uncertain = Shot(1, 1.4, [0.5, 0.5], "forehand", confidence=0.2)
    reliable = Shot(2, 2.4, [0.9, 0.2], "backhand", reviewed=True)
    missing = Shot(3, kind="forehand")
    session = Session("test.mp4", calibration, shots=[uncertain, reliable, missing])
    assert approach_speed_candidate(uncertain, calibration) == 36
    assert approach_speed(uncertain, calibration) is None
    assert session.summary_at(1.2)["strokes"] == 1
    assert session.summary_at(1.2)["hit_rate"] is None
    assert session.summary_at(1.5)["hit_rate"] == 100
    assert session.summary_at(2.2)["speed_count"] == 0
    at_end = session.summary_at(4)
    assert at_end["strokes"] == 3
    assert at_end["forehand"] == 2
    assert at_end["backhand"] == 1
    assert at_end["hit_rate"] == 50
    assert at_end["approach_kmh"] == 36
    assert at_end["speed_count"] == 1


def test_speed_summary_groups_only_reliable_included_strokes(calibration):
    calibration.distance_m = 4
    calibration.fixed_contact_plane = True
    session = Session(
        "test.mp4",
        calibration,
        shots=[
            Shot(1, 1.4, kind="forehand", reviewed=True),
            Shot(2, 2.2, kind="forehand", reviewed=True),
            Shot(3, 3.5, kind="backhand", reviewed=True),
            Shot(4, 4.4, kind="unknown", reviewed=True),
            Shot(5, 5.1, kind="backhand", confidence=0.1),
            Shot(6, 6.1, kind="backhand", reviewed=True, included=False),
        ],
    )
    summary = session.summary()
    assert summary["approach_kmh"] == 43.2
    assert summary["peak_kmh"] == 72
    assert summary["forehand_kmh"] == 54
    assert summary["backhand_kmh"] == 28.8


def test_unknowns_and_excluded_do_not_change_hit_denominator(calibration):
    s = Session("test.mp4", calibration)
    s.shots = [
        Shot(0, 0.3, [0.5, 0.5], "forehand"),
        Shot(1, 1.3, [0.9, 0.2], "backhand"),
        Shot(2),
        Shot(3, 3.3, [0.5, 0.5], included=False),
    ]
    assert s.summary()["strokes"] == 3
    assert s.summary()["hit_rate"] == 50
    assert s.summary()["hits"] == 1
    assert s.summary()["unlocalized"] == 1
    assert s.summary()["unknown"] == 1


def test_no_contacts_is_missing_not_zero(calibration):
    summary = Session("test.mp4", calibration).summary()
    assert summary["hit_rate"] is None
    assert summary["approach_kmh"] is None
    assert summary["peak_kmh"] is None
    assert summary["forehand_kmh"] is None
    assert summary["backhand_kmh"] is None


def test_storage_preserves_original_detections(tmp_path, calibration):
    s = Session("test.mp4", calibration)
    s.shots = [Shot(1, 1.5, [0.5, 0.5])]
    s.automatic_shots = deepcopy(s.shots)
    s.shots[0].kind = "forehand"
    s.shots[0].reviewed = True
    store = SessionStore(tmp_path)
    store.save(s)
    loaded = store.load(s.id)
    assert loaded.shots[0].kind == "forehand"
    assert loaded.automatic_shots[0].kind == "unknown"
    assert len(store.list()) == 1
    export_json(loaded, tmp_path / "out.json")
    export_csv(loaded, tmp_path / "out.csv")
    assert json.loads((tmp_path / "out.json").read_text("utf-8"))["schema_version"] == 1
    assert "approach_kmh_estimate" in (tmp_path / "out.csv").read_text("utf-8-sig")


def test_delete_session_removes_backups_and_preserves_source(tmp_path, calibration):
    video = tmp_path / "source.mp4"
    video.write_bytes(b"source")
    session = Session(str(video), calibration)
    store = SessionStore(tmp_path / "sessions")
    store.save(session)
    (store.root / session.id / "session.backup.json").write_text("backup")
    store.delete(session.id)
    assert store.list() == []
    assert not (store.root / session.id).exists()
    assert video.read_bytes() == b"source"
    unrelated = store.root / "assets"
    unrelated.mkdir()
    store.delete("assets")
    assert unrelated.is_dir()
    for invalid_id in ("", "..", "../source.mp4"):
        with pytest.raises(ValueError):
            store.delete(invalid_id)
    assert video.is_file()


def test_serial_protocol_has_null_measurements_and_one_line(calibration):
    packet = display_packet(Session("test.mp4", calibration))
    assert packet.count(b"\n") == 1
    assert len(packet) < 768
    parsed = json.loads(packet)
    assert parsed["v"] == 1
    assert parsed["hit_rate"] is None
    assert parsed["approach_kmh"] is None


def test_unsupported_schema_rejected(calibration):
    d = Session("test.mp4", calibration).to_dict()
    d["schema_version"] = 99
    with pytest.raises(ValueError):
        Session.from_dict(d)
