"""Evaluate on completely reviewed held-out sessions, never synthetic UI labels."""

import math

from .domain import Session


def match_events(predicted, truth, tolerance):
    # Monotonic earliest-feasible matching maximizes cardinality for ordered time
    # events with a fixed tolerance; nearest-first matching can lose valid pairs.
    predicted = sorted(enumerate(predicted), key=lambda x: x[1])
    truth = sorted(enumerate(truth), key=lambda x: x[1])
    p = g = 0
    matches = []
    while p < len(predicted) and g < len(truth):
        pi, pt = predicted[p]
        gi, gt = truth[g]
        if pt < gt - tolerance:
            p += 1
        elif pt > gt + tolerance:
            g += 1
        else:
            matches.append((pi, gi, abs(pt - gt)))
            p += 1
            g += 1
    return matches


def event_scores(predicted, truth, tolerance):
    matches = match_events(predicted, truth, tolerance)
    tp = len(matches)
    precision = tp / len(predicted) if predicted else (0 if truth else None)
    recall = tp / len(truth) if truth else None
    f1 = 2 * tp / (len(predicted) + len(truth)) if predicted or truth else None
    return {
        "tp": tp,
        "fp": len(predicted) - tp,
        "fn": len(truth) - tp,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }, matches


def evaluate(session: Session, tolerance=0.08) -> dict:
    truth = [s for s in session.shots if s.included]
    if any(not s.reviewed for s in truth):
        raise ValueError("Referans oturumdaki bütün dahil edilmiş vuruşlar incelenmiş olmalı.")
    if session.id == "syntheticdemo":
        raise ValueError("Sentetik arayüz örneği saha doğruluğu için kullanılamaz.")
    predicted = session.automatic_shots
    contacts, matches = event_scores(
        [s.contact_t for s in predicted], [s.contact_t for s in truth], tolerance
    )
    walls, _ = event_scores(
        [s.wall_t for s in predicted if s.wall_t is not None],
        [s.wall_t for s in truth if s.wall_t is not None],
        tolerance,
    )
    classified = [
        (predicted[p], truth[g])
        for p, g, _ in matches
        if predicted[p].kind != "unknown" and truth[g].kind != "unknown"
    ]
    known_truth = sum(s.kind != "unknown" for s in truth)
    errors = [
        math.dist(predicted[p].wall_xy, truth[g].wall_xy)
        for p, g, _ in matches
        if predicted[p].wall_xy is not None and truth[g].wall_xy is not None
    ]
    return {
        "tolerance_seconds": tolerance,
        "reference_strokes": len(truth),
        "racket_contacts": contacts,
        "wall_contacts": walls,
        "classification_coverage": len(classified) / known_truth if known_truth else None,
        "classification_accuracy": sum(p.kind == g.kind for p, g in classified) / len(classified)
        if classified
        else None,
        "placement_mean_normalized_error": sum(errors) / len(errors) if errors else None,
        "placement_evaluated": len(errors),
        "speed_validated": False,
    }
