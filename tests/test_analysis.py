import numpy as np
import pytest

from tennis_tracking.analysis import AnalysisCancelled, CameraMonitor, analyze, classify, detect_shots
from tennis_tracking.detection import BallTracker, Candidate, ColorDetector, RFDETRDetector
from tennis_tracking.domain import Sample, Session


def pose():
    values = [[0.5, 0.5, 0] for _ in range(33)]
    values[11] = [0.4, 0.3, 0.9]
    values[12] = [0.6, 0.3, 0.9]
    return values


def test_handedness_front_back_and_occlusion(calibration):
    sample = Sample(0, ball=[0.8, 0.4], pose=pose())
    assert classify(sample, calibration) == "forehand"
    calibration.handedness = "left"
    assert classify(sample, calibration) == "backhand"
    sample.pose[11], sample.pose[12] = sample.pose[12], sample.pose[11]
    assert classify(sample, calibration) == "forehand"
    sample.pose[11][2] = 0.1
    assert classify(sample, calibration) == "unknown"


def test_midline_is_unknown(calibration):
    sample = Sample(0, ball=[0.5, 0.4], pose=pose())
    assert classify(sample, calibration) == "unknown"


def test_tracker_coasts_briefly_but_never_marks_prediction_observed():
    tracker = BallTracker()
    tracker.update(0, [Candidate([0.2, 0.3], 0.01, 0.9)])
    sample = tracker.update(0.03, [])
    assert sample.ball is not None
    assert not sample.observed
    assert tracker.update(0.3, []).ball is None


def test_tracker_does_not_jump_to_distant_decoy():
    tracker = BallTracker()
    tracker.update(0, [Candidate([0.2, 0.3], 0.01, 0.9)])
    result = tracker.update(0.03, [Candidate([0.85, 0.8], 0.01, 0.99), Candidate([0.21, 0.3], 0.01, 0.5)])
    assert result.ball == [0.21, 0.3]


def trajectory():
    # One racket reversal at .2s, one wall reversal at .6s. Real measurements only.
    result = []
    for i in range(61):
        t = i / 60
        if t < 0.2:
            x = 0.65 + t * 0.75
        elif t < 0.6:
            x = 0.8 - (t - 0.2) * 1.25
        else:
            x = 0.3 + (t - 0.6) * 0.8
        result.append(
            Sample(
                t,
                [x, 0.4],
                radius=0.01,
                confidence=0.9,
                observed=True,
                racket=[0.75, 0.3, 0.85, 0.5] if 0.12 < t < 0.28 else None,
            )
        )
    return result


def test_strike_wall_pair_and_no_double_count(calibration):
    shots = detect_shots(trajectory(), calibration)
    assert len(shots) == 1
    assert shots[0].contact_t == pytest.approx(0.2, abs=0.04)
    assert shots[0].wall_t == pytest.approx(0.6, abs=0.04)
    assert shots[0].wall_xy is not None


def test_wall_placement_uses_camera_aligned_ball(calibration):
    samples = trajectory()
    for sample in samples:
        if sample.t >= 0.4 and sample.ball is not None:
            sample.reference_ball = [sample.ball[0] - 0.05, sample.ball[1]]
    shots = detect_shots(samples, calibration)
    assert len(shots) == 1
    assert shots[0].wall_xy[0] == pytest.approx(0.3, abs=0.06)


def test_wall_vertical_turn_counts_when_ball_keeps_moving_sideways(calibration):
    samples = []
    for i in range(61):
        t = i / 60
        x = 0.7 + t * 0.5 if t < 0.2 else 0.8 - (t - 0.2) * 0.6
        y = 0.6 if t < 0.2 else 0.4 + abs(t - 0.6) * 0.5
        samples.append(
            Sample(
                t,
                [x, y],
                radius=0.008,
                confidence=0.9,
                observed=True,
                racket=[0.75, 0.45, 0.85, 0.65] if 0.12 < t < 0.28 else None,
            )
        )
    shots = detect_shots(samples, calibration)
    assert len(shots) == 1
    assert shots[0].wall_t == pytest.approx(0.6, abs=0.05)


def test_no_strike_from_unobserved_predictions(calibration):
    samples = trajectory()
    for sample in samples:
        sample.observed = False
    assert detect_shots(samples, calibration) == []


def test_wall_turn_without_racket_evidence_is_not_a_stroke(calibration):
    samples = trajectory()
    for sample in samples:
        sample.racket = None
    assert detect_shots(samples, calibration) == []


def test_racket_contact_is_counted_even_when_wall_impact_is_missing(calibration):
    samples = trajectory()[:31]
    shots = detect_shots(samples, calibration)
    assert len(shots) == 1
    assert shots[0].wall_t is None
    assert shots[0].wall_xy is None


def test_pose_reach_finds_contact_without_ball_touching_wrist(calibration):
    samples = trajectory()[:31]
    for sample in samples:
        sample.racket = None
        sample.pose = pose()
        sample.pose[16] = [0.68, 0.4, 0.95]
    shots = detect_shots(samples, calibration)
    assert len(shots) == 1
    assert shots[0].contact_t == pytest.approx(0.2, abs=0.05)


def test_briefly_missing_ball_at_contact_keeps_candidate(calibration):
    samples = trajectory()
    for sample in samples:
        if abs(sample.t - 0.2) < 0.02:
            sample.observed = False
    shots = detect_shots(samples, calibration)
    assert len(shots) == 1
    assert shots[0].contact_t == pytest.approx(0.2, abs=0.06)


def test_ball_bounce_below_wrist_is_not_racket_contact(calibration):
    samples = trajectory()[:31]
    for sample in samples:
        sample.racket = None
        sample.pose = pose()
        sample.pose[16] = [0.8, 0.15, 0.95]
        sample.ball[1] = 0.8
    assert detect_shots(samples, calibration) == []


def test_small_camera_drift_keeps_wall_mapping_available():
    import cv2

    rng = np.random.default_rng(7)
    frame = rng.integers(0, 256, (180, 320, 3), dtype=np.uint8)
    shifted = cv2.warpAffine(frame, np.float32([[1, 0, 14], [0, 1, 0]]), (320, 180))
    camera = CameraMonitor()
    assert not camera.update(frame)
    for _ in range(3):
        assert not camera.update(shifted)
    assert camera.drift
    assert camera.reference_point([0.5 + 14 / 320, 0.5]) == pytest.approx([0.5, 0.5], abs=0.01)


def test_large_camera_move_disables_fixed_wall_mapping():
    import cv2

    rng = np.random.default_rng(7)
    frame = rng.integers(0, 256, (180, 320, 3), dtype=np.uint8)
    shifted = cv2.warpAffine(frame, np.float32([[1, 0, 28], [0, 1, 0]]), (320, 180))
    camera = CameraMonitor()
    camera.update(frame)
    assert [camera.update(shifted) for _ in range(3)] == [False, False, True]


def test_color_detector_rejects_static_mark_after_warmup():
    import cv2

    image = np.zeros((200, 300, 3), dtype=np.uint8)
    cv2.circle(image, (70, 70), 6, (40, 220, 210), -1)
    detector = ColorDetector()
    for _ in range(10):
        candidates, _ = detector.detect(image)
    assert not candidates


def test_missing_neural_model_is_explicit_error(tmp_path):
    with pytest.raises(ValueError, match="model"):
        RFDETRDetector(str(tmp_path / "missing.pth"))


def test_cancel_keeps_caller_responsible_for_previous_session(demo):
    s = Session(demo.video_path, demo.calibration)
    with pytest.raises(AnalysisCancelled):
        analyze(s, cancelled=lambda: True)


def test_color_pipeline_reads_video_and_returns_honest_warnings(demo):
    from copy import deepcopy

    s = Session(demo.video_path, deepcopy(demo.calibration))
    result = analyze(s)
    assert result.status == "complete"
    assert len(result.samples) == 300
    assert sum(x.observed for x in result.samples) > 40
    assert result.shots == []  # No racket/pose detector in this test.
    assert any("Deneysel" in w for w in result.warnings)
