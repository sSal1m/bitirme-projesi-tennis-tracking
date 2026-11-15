"""Calibration UX: corner order is enforced, corners can be corrected by
dragging, and the target rectangle has handles, numeric fields, reset and undo."""

from copy import deepcopy

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtTest import QTest

from tennis_tracking.app import MainWindow
from tennis_tracking.domain import (
    WALL_CORNER_PROBLEMS,
    Calibration,
    wall_corner_problem,
)

VALID_WALL = [[0.35, 0.13], [0.69, 0.13], [0.69, 0.57], [0.35, 0.57]]


# --------------------------------------------------------------------------
# (a) corner order
# --------------------------------------------------------------------------
def test_valid_corner_order_is_accepted():
    assert wall_corner_problem(VALID_WALL) is None
    Calibration(wall=VALID_WALL).validate()


def test_crossed_corners_are_detected():
    crossed = [[0.1, 0.1], [0.6, 0.6], [0.6, 0.1], [0.1, 0.6]]
    assert wall_corner_problem(crossed) == "crossed"
    with pytest.raises(ValueError, match="çapraz"):
        Calibration(wall=crossed).validate()


def test_reversed_corners_are_detected():
    reversed_wall = [[0.35, 0.57], [0.69, 0.57], [0.69, 0.13], [0.35, 0.13]]
    assert wall_corner_problem(reversed_wall) == "reversed"
    with pytest.raises(ValueError, match="ters sırada"):
        Calibration(wall=reversed_wall).validate()


@pytest.mark.parametrize(
    "rotated",
    [
        [[0.69, 0.13], [0.69, 0.57], [0.35, 0.57], [0.35, 0.13]],  # quarter turn
        [[0.69, 0.57], [0.35, 0.57], [0.35, 0.13], [0.69, 0.13]],  # half turn
        [[0.35, 0.57], [0.35, 0.13], [0.69, 0.13], [0.69, 0.57]],  # three quarter
    ],
)
def test_rotated_corners_are_detected(rotated):
    assert wall_corner_problem(rotated) == "rotated"
    with pytest.raises(ValueError, match="döndürülmüş"):
        Calibration(wall=rotated).validate()


def test_every_problem_has_a_message_naming_the_expected_order():
    for message in WALL_CORNER_PROBLEMS.values():
        assert "TL" in message and "TR" in message and "BR" in message and "BL" in message


def test_perspective_wall_from_a_real_recording_is_accepted():
    """The quad measured on clip_08/clip_09 must survive the stricter check."""
    wall = [[0.375, 0.1296], [0.6927, 0.1296], [0.6927, 0.5741], [0.375, 0.5741]]
    assert wall_corner_problem(wall) is None
    slanted = [[0.354, 0.136], [0.684, 0.111], [0.686, 0.606], [0.361, 0.606]]
    assert wall_corner_problem(slanted) is None


def test_invalid_corners_are_kept_instead_of_being_cleared(qapp, tmp_path, demo, monkeypatch):
    window = MainWindow(tmp_path)
    window.open_session(deepcopy(demo))
    notices = []
    monkeypatch.setattr(window, "notify", lambda text: notices.append(text))
    # Three corners placed in the wrong order already, the fourth click closes
    # the loop but with a rotated assignment.
    window.canvas.points = [[0.69, 0.13], [0.69, 0.57], [0.35, 0.57]]
    window.canvas.mode = "calibrate"
    window.canvas_clicked(0.35, 0.13)
    assert len(window.canvas.points) == 4, "hatalı köşeler silinmemeli"
    assert notices, "hata mesajı gösterilmeli"
    assert "Sırayı düzelt" in notices[-1]
    assert window.canvas.mode == "calibrate"
    window.close()


# --------------------------------------------------------------------------
# (b) corners can be corrected by dragging
# --------------------------------------------------------------------------
def _canvas_with_wall(window, wall):
    window.canvas.mode = "view"
    window.session.calibration.wall = [list(point) for point in wall]
    window.canvas.resize(600, 400)
    window.canvas.show()
    QTest.qWait(30)
    return window.canvas


def test_dragging_a_corner_updates_the_calibration(qapp, tmp_path, demo):
    window = MainWindow(tmp_path)
    window.open_session(deepcopy(demo))
    canvas = _canvas_with_wall(window, VALID_WALL)
    before = list(window.session.calibration.wall[1])
    spot = canvas.image_rect()
    position = QPointF(
        spot.x() + before[0] * spot.width(), spot.y() + before[1] * spot.height()
    )
    assert canvas.corner_at(position) == 1
    canvas.set_corner(1, 0.70, 0.20)
    assert window.session.calibration.wall[1] == [0.70, 0.20]
    window.close()


def test_corner_drag_emits_the_new_position(qapp, tmp_path, demo):
    window = MainWindow(tmp_path)
    window.open_session(deepcopy(demo))
    canvas = _canvas_with_wall(window, VALID_WALL)
    seen = []
    canvas.corner_moved.connect(lambda index, x, y: seen.append((index, x, y)))
    canvas.set_corner(0, 0.30, 0.10)
    assert seen == [(0, 0.30, 0.10)]
    window.close()


def test_arrow_keys_nudge_the_selected_corner_by_one_pixel(qapp, tmp_path, demo):
    window = MainWindow(tmp_path)
    window.open_session(deepcopy(demo))
    canvas = _canvas_with_wall(window, VALID_WALL)
    canvas.selected_index = 0
    rect = canvas.image_rect()
    before = list(window.session.calibration.wall[0])
    key = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Right, Qt.NoModifier)
    QTest.keyClick(canvas, Qt.Key_Right)
    after = window.session.calibration.wall[0]
    assert after[0] - before[0] == pytest.approx(1 / rect.width(), rel=1e-6)
    assert after[1] == pytest.approx(before[1])
    assert key.key() == Qt.Key_Right


def test_shift_arrow_nudges_by_ten_pixels(qapp, tmp_path, demo):
    window = MainWindow(tmp_path)
    window.open_session(deepcopy(demo))
    canvas = _canvas_with_wall(window, VALID_WALL)
    canvas.selected_index = 0
    rect = canvas.image_rect()
    before = list(window.session.calibration.wall[0])
    QTest.keyClick(canvas, Qt.Key_Down, Qt.ShiftModifier)
    after = window.session.calibration.wall[0]
    assert after[1] - before[1] == pytest.approx(10 / rect.height(), rel=1e-6)


def test_a_broken_corner_is_reported_while_dragging(qapp, tmp_path, demo, monkeypatch):
    window = MainWindow(tmp_path)
    window.open_session(deepcopy(demo))
    canvas = _canvas_with_wall(window, VALID_WALL)
    notices = []
    monkeypatch.setattr(window, "notify", lambda text: notices.append(text))
    canvas.set_corner(1, 0.35, 0.57)  # moves TR onto BL -> the loop breaks
    assert notices, "bozuk köşe için açıklama gösterilmeli"
    assert "Sırayı düzelt" in notices[-1]


# --------------------------------------------------------------------------
# (c) target handles, numeric fields, reset and undo
# --------------------------------------------------------------------------
def test_target_corner_handle_resizes_the_target(qapp, tmp_path, demo):
    window = MainWindow(tmp_path)
    window.open_session(deepcopy(demo))
    chart = window.wall_chart
    chart.resize(500, 200)
    chart.show()
    QTest.qWait(30)
    corners, _ = chart.handle_positions()
    chart.drag_mode = ("corner", 0)
    chart.drag_start = chart.normalized(corners[0])
    chart.drag_original = list(chart.target)
    chart.update_drag(corners[0] + QPointF(40, 30))
    assert chart.target[0] != chart.drag_original[0]
    assert chart.target[2] == pytest.approx(chart.drag_original[2])
    window.close()


def test_target_edge_handle_resizes_only_that_edge(qapp, tmp_path, demo):
    window = MainWindow(tmp_path)
    window.open_session(deepcopy(demo))
    chart = window.wall_chart
    chart.resize(500, 200)
    chart.show()
    QTest.qWait(30)
    _, midpoints = chart.handle_positions()
    chart.drag_mode = ("edge", 0)  # top edge
    chart.drag_start = chart.normalized(midpoints[0])
    chart.drag_original = list(chart.target)
    chart.update_drag(midpoints[0] + QPointF(0, 25))
    assert chart.target[1] != pytest.approx(chart.drag_original[1])
    assert chart.target[0] == pytest.approx(chart.drag_original[0])
    assert chart.target[2] == pytest.approx(chart.drag_original[2])
    window.close()


def test_dragging_inside_the_target_moves_it(qapp, tmp_path, demo):
    window = MainWindow(tmp_path)
    window.open_session(deepcopy(demo))
    chart = window.wall_chart
    chart.resize(500, 200)
    chart.show()
    QTest.qWait(30)
    corners, _ = chart.handle_positions()
    centre = QPointF(
        (corners[0].x() + corners[2].x()) / 2, (corners[0].y() + corners[2].y()) / 2
    )
    chart.drag_mode = ("move", None)
    chart.drag_start = chart.normalized(centre)
    chart.drag_original = list(chart.target)
    chart.update_drag(centre + QPointF(30, 0))
    assert chart.target[0] != pytest.approx(chart.drag_original[0])
    assert chart.target[2] - chart.target[0] == pytest.approx(
        chart.drag_original[2] - chart.drag_original[0]
    )
    window.close()


def test_numeric_target_fields_are_written_into_the_session(qapp, tmp_path, demo):
    window = MainWindow(tmp_path)
    window.open_session(deepcopy(demo))
    window.target_spins[0].setValue(0.40)
    window.target_spins[1].setValue(0.35)
    window.target_spins[2].setValue(0.75)
    window.target_spins[3].setValue(0.60)
    target = window.session.calibration.target
    assert target[0] == pytest.approx(0.40)
    assert target[1] == pytest.approx(0.35)
    assert target[2] == pytest.approx(0.75)
    assert target[3] == pytest.approx(0.60)
    window.close()


def test_reset_button_restores_the_default_target(qapp, tmp_path, demo):
    window = MainWindow(tmp_path)
    window.open_session(deepcopy(demo))
    window.target_spins[0].setValue(0.1)
    assert window.session.calibration.target[0] == pytest.approx(0.1)
    window.reset_target()
    assert window.session.calibration.target == pytest.approx([0.3, 0.3, 0.7, 0.7])
    window.close()


def test_undo_button_restores_the_previous_target(qapp, tmp_path, demo):
    window = MainWindow(tmp_path)
    window.open_session(deepcopy(demo))
    window.target_spins[0].setValue(0.10)
    assert window.session.calibration.target[0] == pytest.approx(0.10)
    window.undo_target()
    assert window.session.calibration.target[0] == pytest.approx(0.30)
    assert window.session.calibration.target[2] == pytest.approx(0.70)
    window.close()


def test_undo_steps_back_through_several_changes(qapp, tmp_path, demo):
    window = MainWindow(tmp_path)
    window.open_session(deepcopy(demo))
    window.target_spins[0].setValue(0.10)
    window.target_spins[2].setValue(0.90)
    window.undo_target()
    assert window.session.calibration.target[0] == pytest.approx(0.10)
    window.undo_target()
    assert window.session.calibration.target[0] == pytest.approx(0.30)
    assert window.session.calibration.target[2] == pytest.approx(0.70)
    window.close()


def test_undo_without_history_explains_itself(qapp, tmp_path, demo, monkeypatch):
    window = MainWindow(tmp_path)
    window.open_session(deepcopy(demo))
    notices = []
    monkeypatch.setattr(window, "notify", lambda text: notices.append(text))
    window.undo_target()
    assert notices and "Geri alınacak" in notices[-1]
    window.close()


def test_target_fields_follow_a_change_made_on_the_chart(qapp, tmp_path, demo):
    window = MainWindow(tmp_path)
    window.open_session(deepcopy(demo))
    window.change_target([0.20, 0.25, 0.80, 0.85])
    values = [field.value() for field in window.target_spins]
    assert values == pytest.approx([0.20, 0.25, 0.80, 0.85])
    window.close()


def test_opening_a_session_does_not_rewrite_the_target(qapp, tmp_path, demo):
    """The numeric fields must not feed back into the session while loading."""
    session = deepcopy(demo)
    session.calibration.target = [0.585, 0.595, 0.733, 0.932]
    window = MainWindow(tmp_path)
    window.open_session(session)
    assert window.session.calibration.target == pytest.approx([0.585, 0.595, 0.733, 0.932])
    assert window.target_history == []
    window.close()


def test_loupe_is_drawn_when_a_corner_is_hovered(qapp, tmp_path, demo):
    window = MainWindow(tmp_path)
    window.open_session(deepcopy(demo))
    canvas = _canvas_with_wall(window, VALID_WALL)
    canvas.hover_index = 0
    canvas.mouse_pos = QPointF(canvas.image_rect().center())
    image = canvas.grab()
    assert not image.isNull()
    window.close()
