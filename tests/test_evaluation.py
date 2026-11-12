from copy import deepcopy

import pytest

from tennis_tracking.domain import Session, Shot
from tennis_tracking.evaluation import evaluate, match_events


def test_matching_does_not_lose_valid_pairs_to_greedy_nearest():
    matches = match_events([0.075, 0.15], [0, 0.1], 0.08)
    assert len(matches) == 2


def test_duplicates_and_missed_events_count(calibration):
    session = Session("test.mp4", calibration)
    session.shots = [
        Shot(1, 1.3, [0.4, 0.5], "forehand", reviewed=True),
        Shot(2, 2.3, [0.5, 0.6], "backhand", reviewed=True),
    ]
    session.automatic_shots = [Shot(1.02, 1.32, [0.4, 0.5], "forehand"), Shot(1.04, 1.35)]
    result = evaluate(session)
    assert result["racket_contacts"]["tp"] == 1
    assert result["racket_contacts"]["fp"] == 1
    assert result["racket_contacts"]["fn"] == 1
    assert result["classification_coverage"] == 0.5
    assert result["classification_accuracy"] == 1
    assert result["speed_validated"] is False


def test_rejects_unreviewed_ground_truth(calibration):
    session = Session("test.mp4", calibration, shots=[Shot(1)])
    with pytest.raises(ValueError):
        evaluate(session)


def test_synthetic_demo_cannot_be_evidence(demo):
    with pytest.raises(ValueError):
        evaluate(deepcopy(demo))
