from copy import deepcopy
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox

from tennis_tracking.app import HelpHeader, MainWindow


def test_play_button_uses_playback_icons(qapp, tmp_path):
    window = MainWindow(tmp_path)
    assert window.play_btn.text() == ""
    assert not window.play_btn.icon().isNull()
    play_icon = window.play_btn.icon().cacheKey()
    assert window.play_btn.toolTip() == "Oynat"
    window.player.playbackStateChanged.emit(QMediaPlayer.PlayingState)
    assert window.play_btn.icon().cacheKey() != play_icon
    assert window.play_btn.accessibleName() == "Duraklat"
    window.player.playbackStateChanged.emit(QMediaPlayer.StoppedState)
    assert window.play_btn.toolTip() == "Oynat"
    window.close()


def test_delete_open_history_session_clears_results_but_keeps_video(qapp, tmp_path, demo, monkeypatch):
    window = MainWindow(tmp_path)
    session = deepcopy(demo)
    other = deepcopy(demo)
    other.id = "other"
    window.store.save(other)
    window.store.save(session)
    window.open_session(session)
    window.refresh_history()
    for index in range(window.history.count()):
        item = window.history.item(index)
        if item.data(Qt.UserRole) == session.id:
            window.history.setCurrentItem(item)
            break
    assert window.delete_history_btn.isEnabled()
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.Yes)
    window.delete_history_btn.click()
    assert [row['id'] for row in window.store.list()] == [other.id]
    assert window.history.count() == window.comparison.rowCount() == 1
    assert not (tmp_path / session.id).exists()
    assert window.session is None and window.video_path is None
    assert window.canvas.image.isNull()
    assert window.shot_table.rowCount() == 0
    assert all(card.value.text() == "—" for card in window.cards + window.live_cards)
    window.persist()
    assert len(window.store.list()) == 1
    assert window.store.load(other.id).video_path == demo.video_path
    assert Path(demo.video_path).is_file()
    window.close()


def test_cancel_history_deletion_keeps_session(qapp, tmp_path, demo, monkeypatch):
    window = MainWindow(tmp_path)
    window.store.save(demo)
    window.refresh_history()
    window.history.setCurrentRow(0)
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.No)
    window.delete_history_btn.click()
    assert len(window.store.list()) == 1
    assert (tmp_path / demo.id / "session.json").exists()
    window.close()


def test_review_and_history_roundtrip(qapp, tmp_path, demo):
    window = MainWindow(tmp_path)
    window.open_session(deepcopy(demo))
    assert window.cards[0].value.text() == "5"
    window.shot_table.selectRow(0)
    window.kind.setCurrentIndex(2)
    window.save_shot()
    loaded = window.store.load(demo.id)
    assert loaded.shots[0].kind == "backhand"
    assert loaded.shots[0].reviewed
    window.toggle_shot()
    assert window.session.summary()["strokes"] == 4
    window.close()


def test_target_change_recomputes_hit_rate(qapp, tmp_path, demo):
    window = MainWindow(tmp_path)
    window.open_session(deepcopy(demo))
    window.change_target([0, 0, 1, 1])
    assert window.session.summary()["hit_rate"] == 100
    window.close()


def test_camera_drift_marks_placement_as_approximate(qapp, tmp_path, demo):
    session = deepcopy(demo)
    session.warnings.append("Hafif kamera kayması saptandı: hedef isabeti yaklaşık değerdir.")
    window = MainWindow(tmp_path)
    window.open_session(session)
    assert window.cards[2].value.text() == "%80"
    assert "Kamera kayması" in window.cards[2].hint.text()
    window.close()


def test_wall_marker_opens_exact_impact_frame(qapp, tmp_path, demo):
    window = MainWindow(tmp_path)
    window.open_session(deepcopy(demo))
    window.show()
    qapp.processEvents()
    shot = window.session.shots[0]
    marker = window.wall_chart.wall_to_plot(shot.wall_xy)
    point = QPoint(round(marker.x()), round(marker.y()))
    QTest.mouseClick(window.wall_chart, Qt.LeftButton, pos=point)
    assert window.edit_id == shot.id
    assert window.canvas.t == shot.wall_t
    window.close()


def test_review_headers_explain_timing_and_source(qapp, tmp_path, demo):
    window = MainWindow(tmp_path)
    window.open_session(deepcopy(demo))
    assert window.cards[1].value.text() == "4 - 1"
    assert isinstance(window.shot_table.horizontalHeader(), HelpHeader)
    for column, term in [(1, "rakete"), (2, "duvara"), (5, "Otomatik")]:
        header = window.shot_table.horizontalHeaderItem(column)
        assert column in window.shot_table.horizontalHeader().help_columns
        assert term in header.toolTip()
    window.close()


def test_wall_chart_uses_video_wall_geometry(qapp, tmp_path, demo):
    window = MainWindow(tmp_path)
    window.open_session(deepcopy(demo))
    window.show()
    qapp.processEvents()
    calibration = window.session.calibration
    chart = window.wall_chart
    x0, y0, x1, y1 = chart.wall_bounds()
    expected_aspect = (x1 - x0) * window.session.width / ((y1 - y0) * window.session.height)
    assert chart.plot_rect().width() / chart.plot_rect().height() == pytest.approx(expected_aspect)
    for chart_point, image_point in zip(chart.wall_polygon(), calibration.wall):
        assert chart.plot_to_image(chart_point) == pytest.approx(image_point)
    for chart_point, image_point in zip(chart.target_polygon(), calibration.target_polygon()):
        assert chart.plot_to_image(chart_point) == pytest.approx(image_point)
    for chart_point, wall_xy in zip(
        chart.target_polygon(),
        ([calibration.target[0], calibration.target[1]], [calibration.target[2], calibration.target[1]],
         [calibration.target[2], calibration.target[3]], [calibration.target[0], calibration.target[3]]),
    ):
        assert chart.normalized(chart_point) == pytest.approx(wall_xy, abs=1e-5)
    window.close()


def test_dragged_wall_target_updates_video_target(qapp, tmp_path, demo):
    window = MainWindow(tmp_path)
    window.open_session(deepcopy(demo))
    window.show()
    qapp.processEvents()
    chart = window.wall_chart
    start = chart.wall_to_plot([0.05, 0.05])
    end = chart.wall_to_plot([0.95, 0.95])
    QTest.mousePress(chart, Qt.LeftButton, pos=QPoint(round(start.x()), round(start.y())))
    QTest.mouseRelease(chart, Qt.LeftButton, pos=QPoint(round(end.x()), round(end.y())))
    assert window.session.calibration.target == pytest.approx([0.05, 0.05, 0.95, 0.95], abs=0.02)
    for chart_point, image_point in zip(
        chart.target_polygon(), window.session.calibration.target_polygon()
    ):
        assert chart.plot_to_image(chart_point) == pytest.approx(image_point)
    window.close()


def test_measured_distance_updates_existing_session_speed(qapp, tmp_path, demo):
    session = deepcopy(demo)
    session.calibration.distance_m = None
    session.calibration.fixed_contact_plane = False
    window = MainWindow(tmp_path)
    window.open_session(session)
    assert window.cards[3].value.text() == "—"
    assert "mesafeyi gir" in window.cards[3].hint.text()
    assert "Peak: —" in window.cards[3].hint.text()
    window.distance.setValue(4)
    window.fixed_plane.setChecked(True)
    window.apply_distance()
    assert window.cards[3].value.text() == "36"
    assert "Peak: 36 km/sa" in window.cards[3].hint.text()
    assert "Forehand: 36 km/sa" in window.cards[3].hint.text()
    assert "Backhand: 36 km/sa" in window.cards[3].hint.text()
    assert window.store.load(demo.id).calibration.distance_m == 4
    window.close()


def test_live_metrics_follow_video_position(qapp, tmp_path, demo):
    window = MainWindow(tmp_path)
    window.open_session(deepcopy(demo))
    window.position_changed(0)
    total = window.session.summary()["strokes"]
    assert [card.value.text() for card in window.live_cards] == [
        f"0 / {total}",
        "0 - 0",
        "—",
        "—",
    ]
    window.position_changed(2500)
    current = window.session.summary_at(2.5)
    # The running count is shown next to the total so it cannot be mistaken
    # for the session total.
    assert window.live_cards[0].value.text() == f"{current['strokes']} / {total}"
    assert window.live_cards[1].value.text() == f"{current['forehand']} - {current['backhand']}"
    assert window.live_cards[2].value.text() == f"%{current['hit_rate']:g}"
    assert window.live_cards[3].value.text() == f"{current['approach_kmh']:g}"
    window.position_changed(0)
    assert window.live_cards[0].value.text() == f"0 / {total}"
    window.close()


def test_speed_chart_keeps_every_shot_and_explains_missing_values(qapp, tmp_path, demo):
    session = deepcopy(demo)
    session.shots[0].reviewed = False
    session.shots[0].confidence = 0.2
    session.shots[1].wall_t = None
    window = MainWindow(tmp_path)
    window.open_session(session)
    entries = window.speed_chart.entries()
    assert len(entries) == len(session.shots)
    assert entries[0][1] is not None and entries[0][2] is None
    assert entries[1][1] is None and entries[1][2] is None
    assert window.shot_table.item(0, 4).text().startswith("≈")
    assert window.shot_table.item(1, 4).text() == "—"
    window.apply_distance()
    assert "düşük güvenli" in window.notice.text()
    assert "geçerli duvar zamanı yok" in window.notice.text()
    window.show()
    qapp.processEvents()
    plot = window.speed_chart.chart_rect()
    missing_position = QPoint(
        round(plot.x() + 1.5 * plot.width() / len(entries)), round(plot.center().y())
    )
    QTest.mouseClick(window.speed_chart, Qt.LeftButton, pos=missing_position)
    assert window.edit_id == session.shots[1].id
    window.close()


def test_manual_shot_preserves_unknowns(qapp, tmp_path, demo):
    window = MainWindow(tmp_path)
    window.open_session(deepcopy(demo))
    window.new_shot()
    window.contact_time.setValue(9)
    window.save_shot()
    assert window.session.summary()["unlocalized"] == 1
    assert window.session.shots[-1].wall_t is None
    window.close()


def test_phone_rotation_preview_matches_analysis_dimensions(qapp, tmp_path, calibration):
    from PySide6.QtGui import QColor, QImage
    from PySide6.QtMultimedia import QtVideo, QVideoFrame

    from tennis_tracking.domain import Session

    image = QImage(100, 60, QImage.Format_RGB32)
    image.fill(QColor("red"))
    frame = QVideoFrame(image)
    frame.setRotation(QtVideo.Rotation.Clockwise90)
    window = MainWindow(tmp_path)
    window.session = Session("test.mp4", calibration, width=60, height=100)
    window.video_frame(frame)
    assert window.canvas.image.width() == 60
    assert window.canvas.image.height() == 100
    assert window.canvas.image.pixelColor(30, 50).red() > 200
    window.close()


def test_setup_panel_scrolls_without_clipping_actions(qapp, tmp_path):
    window = MainWindow(tmp_path)
    window.resize(1060, 760)
    window.show()
    qapp.processEvents()
    scrollbar = window.setup_scroll.verticalScrollBar()
    assert scrollbar.maximum() > 0
    assert window.setup_scroll.viewport().width() >= window.setup_panel.minimumSizeHint().width()
    assert window.analyze_btn.mapTo(window.setup_container, QPoint(0, 0)).y() >= 0
    assert (
        window.analyze_btn.mapTo(window.setup_container, QPoint(0, 0)).y() + window.analyze_btn.height()
        <= window.setup_container.height()
    )
    scrollbar.setValue(scrollbar.maximum())
    qapp.processEvents()
    hint_bottom = (
        window.calibration_hint.mapTo(window.setup_scroll.viewport(), QPoint(0, 0)).y()
        + window.calibration_hint.height()
    )
    assert hint_bottom <= window.setup_scroll.viewport().height()
    window.close()


def test_overview_keeps_charts_and_controls_accessible_when_resized(qapp, tmp_path, demo):
    window = MainWindow(tmp_path)
    window.open_session(deepcopy(demo))
    window.show()
    qapp.processEvents()
    overview = window.overview_scroll
    assert overview.horizontalScrollBar().maximum() == 0
    overview.verticalScrollBar().setValue(overview.verticalScrollBar().maximum())
    qapp.processEvents()
    assert window.wall_chart.mapTo(overview.viewport(), window.wall_chart.rect().bottomLeft()).y() <= overview.viewport().height()

    window.resize(1060, 760)
    qapp.processEvents()
    assert overview.horizontalScrollBar().maximum() == 0
    assert overview.verticalScrollBar().maximum() > 0
    assert window.analyze_btn.isVisible()
    overview.verticalScrollBar().setValue(overview.verticalScrollBar().maximum())
    qapp.processEvents()
    assert window.wall_chart.mapTo(overview.viewport(), window.wall_chart.rect().bottomLeft()).y() <= overview.viewport().height()
    window.close()
