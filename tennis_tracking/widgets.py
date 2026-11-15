from __future__ import annotations

import math
from bisect import bisect_left

import cv2
import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QFrame, QLabel, QToolTip, QVBoxLayout, QWidget

from .domain import WALL_CORNER_LABELS, approach_speed, approach_speed_candidate
from .rendering import POSE_EDGES

GREEN = QColor("#215b46")
INK = QColor("#192f27")
MUTED = QColor("#7b8679")
LIME = QColor("#dce895")
PANEL = QColor("#fffefb")
LINE = QColor("#dce4d8")
ORANGE = QColor("#b9712f")


def as_qimage(bgr):
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    return QImage(rgb.data, rgb.shape[1], rgb.shape[0], rgb.strides[0], QImage.Format_RGB888).copy()


class VideoCanvas(QWidget):
    point_clicked = Signal(float, float)
    corner_moved = Signal(int, float, float)

    HANDLE_RADIUS = 13
    LOUPE_SIZE = 132

    def __init__(self):
        super().__init__()
        self.setMinimumSize(388, 260)
        self.image = QImage()
        self.points = []
        self.session = None
        self.mode = "view"
        self.t = 0.0
        self._times = []
        self.drag_index = None
        self.hover_index = None
        self.selected_index = None
        self.mouse_pos = None
        self.loupe_enabled = True
        self.setCursor(Qt.CrossCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setToolTip(
            "Köşeleri sürükle; seçili köşeyi ok tuşlarıyla bir piksel kaydır (Shift: 10 piksel)."
        )

    def set_session(self, session):
        self.session = session
        self._times = [s.t for s in session.samples] if session else []
        self.update()

    def image_rect(self):
        if self.image.isNull():
            return QRectF(self.rect())
        size = self.image.size().scaled(self.size(), Qt.KeepAspectRatio)
        return QRectF(
            (self.width() - size.width()) / 2,
            (self.height() - size.height()) / 2,
            size.width(),
            size.height(),
        )

    def set_image(self, image):
        self.image = image
        self.update()

    def active_points(self) -> list:
        """The corner list the user is currently working on."""
        if self.mode == "calibrate":
            return self.points
        if self.session:
            return self.session.calibration.wall
        return self.points

    def corner_at(self, position) -> int | None:
        """Index of the corner handle under the cursor, if any."""
        points = self.active_points()
        if not points:
            return None
        rect = self.image_rect()
        best = None
        for index, value in enumerate(points):
            spot = QPointF(
                rect.x() + value[0] * rect.width(), rect.y() + value[1] * rect.height()
            )
            distance = (spot.x() - position.x()) ** 2 + (spot.y() - position.y()) ** 2
            if distance <= self.HANDLE_RADIUS**2 and (best is None or distance < best[0]):
                best = (distance, index)
        return best[1] if best else None

    def set_corner(self, index: int, x: float, y: float) -> None:
        points = self.active_points()
        if not (0 <= index < len(points)):
            return
        points[index] = [min(1.0, max(0.0, x)), min(1.0, max(0.0, y))]
        self.corner_moved.emit(index, points[index][0], points[index][1])
        self.update()

    def mousePressEvent(self, event):
        rect = self.image_rect()
        if self.image.isNull() or not rect.contains(event.position()):
            return
        index = self.corner_at(event.position())
        if index is not None:
            self.drag_index = index
            self.selected_index = index
            self.setFocus(Qt.MouseFocusReason)
            self.update()
            return
        if self.mode == "calibrate" and len(self.points) < 4:
            self.point_clicked.emit(
                (event.position().x() - rect.x()) / rect.width(),
                (event.position().y() - rect.y()) / rect.height(),
            )

    def mouseMoveEvent(self, event):
        rect = self.image_rect()
        self.mouse_pos = event.position()
        if self.image.isNull() or not rect.contains(event.position()):
            self.hover_index = None
            self.update()
            return
        if self.drag_index is not None:
            self.set_corner(
                self.drag_index,
                (event.position().x() - rect.x()) / rect.width(),
                (event.position().y() - rect.y()) / rect.height(),
            )
            return
        self.hover_index = self.corner_at(event.position())
        self.update()

    def mouseReleaseEvent(self, event):
        self.drag_index = None
        self.update()

    def keyPressEvent(self, event):
        """Nudge the selected corner one displayed pixel at a time."""
        points = self.active_points()
        if self.selected_index is None or not (0 <= self.selected_index < len(points)):
            super().keyPressEvent(event)
            return
        rect = self.image_rect()
        if rect.isEmpty():
            super().keyPressEvent(event)
            return
        step = 10 if event.modifiers() & Qt.ShiftModifier else 1
        delta = {
            Qt.Key_Left: (-step, 0),
            Qt.Key_Right: (step, 0),
            Qt.Key_Up: (0, -step),
            Qt.Key_Down: (0, step),
        }
        if event.key() not in delta:
            super().keyPressEvent(event)
            return
        dx, dy = delta[event.key()]
        x, y = points[self.selected_index]
        self.set_corner(self.selected_index, x + dx / rect.width(), y + dy / rect.height())
        event.accept()

    def paint_loupe(self, p, rect, cursor) -> None:
        """Magnified inset around the cursor so a corner can be placed precisely."""
        image = self.image
        if image.isNull() or rect.width() < 40 or cursor is None:
            return
        scale = image.width() / rect.width()
        cx = (cursor.x() - rect.x()) * scale
        cy = (cursor.y() - rect.y()) * scale
        span = max(5.0, 22.0 * scale)
        box = float(self.LOUPE_SIZE)
        lx = cursor.x() + 20
        ly = cursor.y() + 20
        if lx + box > self.width() - 4:
            lx = cursor.x() - 20 - box
        if ly + box > self.height() - 4:
            ly = cursor.y() - 20 - box
        target = QRectF(lx, ly, box, box)
        p.save()
        p.setClipRect(target)
        p.drawImage(target, image, QRectF(cx - span, cy - span, 2 * span, 2 * span))
        p.restore()
        p.setPen(QPen(INK, 2))
        p.setBrush(Qt.NoBrush)
        p.drawRect(target)
        p.setPen(QPen(QColor("#d94141"), 1))
        p.drawLine(
            QPointF(target.center().x(), target.top()), QPointF(target.center().x(), target.bottom())
        )
        p.drawLine(
            QPointF(target.left(), target.center().y()), QPointF(target.right(), target.center().y())
        )

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("#173e32"))
        if self.image.isNull():
            p.setPen(QPen(QColor("#48755c"), 1))
            for n in range(1, 7):
                p.drawLine(0, n * self.height() // 7, self.width(), n * self.height() // 7)
                p.drawLine(n * self.width() // 7, 0, n * self.width() // 7, self.height())
            p.setPen(QColor("#e6ecce"))
            p.setFont(QFont("Segoe UI", 24, QFont.Bold))
            p.drawText(self.rect().adjusted(30, 0, -30, -35), Qt.AlignCenter, "Her vuruş bir veri.")
            p.setFont(QFont("Segoe UI", 11))
            p.drawText(
                self.rect().adjusted(30, 50, -30, 0),
                Qt.AlignCenter,
                "Duvar antrenmanını yükle, oyununu daha yakından gör.",
            )
            return
        r = self.image_rect()
        p.drawImage(r, self.image)

        def pt(v):
            return QPointF(r.x() + v[0] * r.width(), r.y() + v[1] * r.height())

        points = (
            self.points
            if self.mode == "calibrate"
            else (self.session.calibration.wall if self.session else self.points)
        )
        if points:
            p.setPen(QPen(LIME, 2))
            polygon = QPolygonF([pt(v) for v in points])
            if len(points) == 4:
                p.drawPolygon(polygon)
            else:
                p.drawPolyline(polygon)
            if len(points) == 4 and self.session and self.mode != "calibrate":
                target = QPolygonF([pt(v) for v in self.session.calibration.target_polygon()])
                p.setPen(QPen(QColor("#dce895"), 2, Qt.DashLine))
                p.setBrush(QColor(220, 232, 149, 45))
                p.drawPolygon(target)
            for n, v in enumerate(points):
                spot = pt(v)
                active = n in (self.hover_index, self.drag_index, self.selected_index)
                p.setPen(QPen(ORANGE if active else GREEN, 3 if active else 1))
                p.setBrush(GREEN if active else QColor("#7fd4a8"))
                p.drawEllipse(spot, 11, 11)
                p.setPen(Qt.white)
                p.drawText(QRectF(spot.x() - 11, spot.y() - 11, 22, 22), Qt.AlignCenter, str(n + 1))
                if n < len(WALL_CORNER_LABELS):
                    tag = QRectF(spot.x() + 13, spot.y() - 27, 26, 17)
                    p.setPen(Qt.NoPen)
                    p.setBrush(QColor(18, 48, 37, 215))
                    p.drawRoundedRect(tag, 4, 4)
                    p.setPen(QColor("#f2f7e4"))
                    p.setFont(QFont("Segoe UI", 9, QFont.Bold))
                    p.drawText(tag, Qt.AlignCenter, WALL_CORNER_LABELS[n])
                    p.setFont(QFont("Segoe UI", 12))
                p.setPen(LIME)
        if self.session and self.mode != "calibrate":
            if self._times:
                i = min(bisect_left(self._times, self.t), len(self._times) - 1)
                sample = self.session.samples[i]
                if abs(sample.t - self.t) < 0.1:
                    previous = None
                    for s in self.session.samples[max(0, i - 12) : i + 1]:
                        if s.ball:
                            p.setPen(
                                QPen(
                                    LIME if s.observed else QColor("#aaaaaa"),
                                    2,
                                    Qt.SolidLine if s.observed else Qt.DashLine,
                                )
                            )
                            if previous and previous.ball and s.observed and previous.observed:
                                p.drawLine(pt(previous.ball), pt(s.ball))
                            p.setBrush(LIME if s.observed else Qt.NoBrush)
                            p.drawEllipse(pt(s.ball), 3, 3)
                        previous = s
                    if sample.pose:
                        p.setPen(QPen(QColor("#f5faed"), 2))
                        for a, b in POSE_EDGES:
                            if min(sample.pose[a][2], sample.pose[b][2]) > 0.6:
                                p.drawLine(pt(sample.pose[a]), pt(sample.pose[b]))
            if len(points) == 4:
                inverse = cv2.getPerspectiveTransform(
                    np.float32([[0, 0], [1, 0], [1, 1], [0, 1]]), np.float32(points)
                )
                number = 0
                for shot in self.session.shots:
                    if not shot.included:
                        continue
                    number += 1
                    if shot.wall_xy is None or shot.wall_t is None or shot.wall_t > self.t:
                        continue
                    xy = cv2.perspectiveTransform(np.float32([[shot.wall_xy]]), inverse)[0, 0]
                    point = pt(xy)
                    p.setPen(QPen(GREEN, 2))
                    p.setBrush(QColor("#f7f7ec"))
                    p.drawEllipse(point, 11, 11)
                    p.drawText(QRectF(point.x() - 11, point.y() - 11, 22, 22), Qt.AlignCenter, str(number))
        p.setPen(Qt.white)
        p.setBrush(QColor(18, 48, 37, 215))
        p.drawRoundedRect(QRectF(r.x() + 12, r.y() + 12, 158, 26), 6, 6)
        p.drawText(
            QRectF(r.x() + 12, r.y() + 12, 158, 26),
            Qt.AlignCenter,
            "KALİBRASYON" if self.mode == "calibrate" else "DUVAR ANTRENMANI",
        )
        if self.loupe_enabled and (self.hover_index is not None or self.drag_index is not None):
            self.paint_loupe(p, r, self.mouse_pos)


class MetricCard(QFrame):
    def __init__(self, title, hint):
        super().__init__()
        self.setObjectName("card")
        self.setMinimumHeight(105)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(17, 12, 17, 12)
        layout.setSpacing(3)
        label = QLabel(title)
        label.setObjectName("eyebrow")
        label.setWordWrap(True)
        self.value = QLabel("—")
        self.value.setObjectName("metric")
        self.hint = QLabel(hint)
        self.hint.setObjectName("muted")
        self.hint.setWordWrap(True)
        layout.addWidget(label)
        layout.addWidget(self.value, 1)
        layout.addWidget(self.hint)


class LiveMetric(QFrame):
    def __init__(self, title, hint):
        super().__init__()
        self.setObjectName("liveMetric")
        self.setToolTip(hint)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(9, 5, 9, 5)
        layout.setSpacing(0)
        label = QLabel(title)
        label.setObjectName("liveLabel")
        self.value = QLabel("—")
        self.value.setObjectName("liveValue")
        layout.addWidget(label)
        layout.addWidget(self.value)


class WallChart(QWidget):
    target_changed = Signal(list)
    shot_clicked = Signal(str)

    HANDLE_RADIUS = 9
    MIN_SIZE = 0.02

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(195)
        self.setMaximumHeight(205)
        self.session = None
        self.target = [0.3, 0.3, 0.7, 0.7]
        self.drag_start = None
        self.drag_mode = None
        self.drag_original = None
        self.setCursor(Qt.CrossCursor)
        self.setMouseTracking(True)

    def plot_rect(self):
        available = QRectF(20, 61, max(10, self.width() - 40), max(10, self.height() - 101))
        bounds = self.wall_bounds()
        if bounds is None:
            return available
        x0, y0, x1, y1 = bounds
        aspect = (x1 - x0) * self.session.width / ((y1 - y0) * self.session.height)
        height = min(available.height(), available.width() / aspect)
        width = height * aspect
        return QRectF(
            available.center().x() - width / 2,
            available.center().y() - height / 2,
            width,
            height,
        )

    def wall_bounds(self):
        if not self.session or len(self.session.calibration.wall) != 4:
            return None
        if self.session.width <= 0 or self.session.height <= 0:
            return None
        points = np.asarray(self.session.calibration.wall, dtype=float)
        x0, y0 = points.min(axis=0)
        x1, y1 = points.max(axis=0)
        if x1 <= x0 or y1 <= y0:
            return None
        return x0, y0, x1, y1

    def image_to_plot(self, xy):
        r = self.plot_rect()
        bounds = self.wall_bounds()
        if bounds is None:
            return QPointF(r.x() + xy[0] * r.width(), r.y() + xy[1] * r.height())
        x0, y0, x1, y1 = bounds
        return QPointF(
            r.x() + (xy[0] - x0) / (x1 - x0) * r.width(),
            r.y() + (xy[1] - y0) / (y1 - y0) * r.height(),
        )

    def plot_to_image(self, pos):
        r = self.plot_rect()
        bounds = self.wall_bounds()
        x = (pos.x() - r.x()) / r.width()
        y = (pos.y() - r.y()) / r.height()
        if bounds is None:
            return [x, y]
        x0, y0, x1, y1 = bounds
        return [x0 + x * (x1 - x0), y0 + y * (y1 - y0)]

    def wall_to_plot(self, xy):
        if self.wall_bounds() is None:
            return self.image_to_plot(xy)
        inverse = cv2.getPerspectiveTransform(
            np.float32([[0, 0], [1, 0], [1, 1], [0, 1]]),
            np.float32(self.session.calibration.wall),
        )
        image_xy = cv2.perspectiveTransform(np.float32([[xy]]), inverse)[0, 0]
        return self.image_to_plot(image_xy)

    def wall_polygon(self):
        if self.wall_bounds() is not None:
            return QPolygonF([self.image_to_plot(xy) for xy in self.session.calibration.wall])
        return QPolygonF([self.image_to_plot(xy) for xy in ([0, 0], [1, 0], [1, 1], [0, 1])])

    def target_polygon(self):
        if self.wall_bounds() is not None:
            return QPolygonF(
                [self.image_to_plot(xy) for xy in self.session.calibration.target_polygon()]
            )
        x0, y0, x1, y1 = self.target
        return QPolygonF(
            [self.image_to_plot(xy) for xy in ([x0, y0], [x1, y0], [x1, y1], [x0, y1])]
        )

    def normalized(self, pos):
        xy = self.plot_to_image(pos)
        if self.wall_bounds() is not None:
            xy = self.session.calibration.wall_point(xy)
        return [min(1, max(0, float(value))) for value in xy]

    def nearest_shot(self, pos):
        if not self.session:
            return None
        nearest = None
        number = 0
        for shot in self.session.shots:
            if not shot.included:
                continue
            number += 1
            if shot.wall_xy is None:
                continue
            point = self.wall_to_plot(shot.wall_xy)
            distance = (pos.x() - point.x()) ** 2 + (pos.y() - point.y()) ** 2
            if nearest is None or distance < nearest[0]:
                nearest = (distance, shot, number)
        return nearest if nearest is not None and nearest[0] <= 12**2 else None

    def handle_positions(self):
        """Corner and edge-midpoint handles of the target, in plot coordinates."""
        polygon = self.target_polygon()
        corners = [QPointF(polygon[i]) for i in range(4)]
        midpoints = []
        for index in range(4):
            a = corners[index]
            b = corners[(index + 1) % 4]
            midpoints.append(QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2))
        return corners, midpoints

    def handle_at(self, pos):
        """Which target handle sits under the cursor, if any."""
        corners, midpoints = self.handle_positions()
        for index, spot in enumerate(corners):
            if math.hypot(spot.x() - pos.x(), spot.y() - pos.y()) <= self.HANDLE_RADIUS:
                return ("corner", index)
        for index, spot in enumerate(midpoints):
            if math.hypot(spot.x() - pos.x(), spot.y() - pos.y()) <= self.HANDLE_RADIUS:
                return ("edge", index)
        return None

    def clamp_target(self, values):
        x0, y0, x1, y1 = values
        x0, x1 = sorted((min(1.0, max(0.0, x0)), min(1.0, max(0.0, x1))))
        y0, y1 = sorted((min(1.0, max(0.0, y0)), min(1.0, max(0.0, y1))))
        if x1 - x0 < self.MIN_SIZE:
            x0 = max(0.0, x1 - self.MIN_SIZE)
        if y1 - y0 < self.MIN_SIZE:
            y0 = max(0.0, y1 - self.MIN_SIZE)
        return [x0, y0, x1, y1]

    def update_drag(self, pos):
        """Live preview while a handle, the target itself or a new box is dragged."""
        end = self.normalized(pos)
        mode, index = self.drag_mode
        sx, sy = self.drag_start
        x0, y0, x1, y1 = self.drag_original
        if mode == "move":
            dx = end[0] - sx
            dy = end[1] - sy
            values = [x0 + dx, y0 + dy, x1 + dx, y1 + dy]
        elif mode == "new":
            values = [min(sx, end[0]), min(sy, end[1]), max(sx, end[0]), max(sy, end[1])]
        elif mode == "corner":
            values = [x0, y0, x1, y1]
            values[index * 2] = end[0]
            values[index * 2 + 1] = end[1]
        else:  # edge: 0 top, 1 right, 2 bottom, 3 left
            values = [x0, y0, x1, y1]
            if index == 0:
                values[1] = end[1]
            elif index == 1:
                values[2] = end[0]
            elif index == 2:
                values[3] = end[1]
            else:
                values[0] = end[0]
        self.target = self.clamp_target(values)
        self.update()

    def mousePressEvent(self, event):
        pos = event.position()
        handle = self.handle_at(pos)
        if handle is not None:
            self.drag_mode = handle
            self.drag_start = self.normalized(pos)
            self.drag_original = list(self.target)
            return
        nearest = self.nearest_shot(pos)
        if nearest is not None:
            self.shot_clicked.emit(nearest[1].id)
            return
        if self.target_polygon().containsPoint(pos, Qt.OddEvenFill):
            self.drag_mode = ("move", None)
            self.drag_start = self.normalized(pos)
            self.drag_original = list(self.target)
            return
        if not self.wall_polygon().containsPoint(pos, Qt.OddEvenFill):
            return
        self.drag_mode = ("new", None)
        self.drag_start = self.normalized(pos)
        self.drag_original = list(self.target)

    def mouseMoveEvent(self, event):
        if self.drag_mode is not None:
            self.update_drag(event.position())
            return
        nearest = self.nearest_shot(event.position())
        if nearest is None:
            QToolTip.hideText()
            return
        _, shot, number = nearest
        x0, y0, x1, y1 = self.target
        hit = x0 <= shot.wall_xy[0] <= x1 and y0 <= shot.wall_xy[1] <= y1
        label = "Hedefte" if hit else "Hedef dışında"
        status = "İncelendi" if shot.reviewed else "Otomatik aday"
        QToolTip.showText(
            event.globalPosition().toPoint(),
            f"{number}. vuruş · {label} · {status} · {shot.wall_t:.2f} sn",
            self,
        )

    def mouseReleaseEvent(self, event):
        if self.drag_mode is not None:
            # A press and release without any move in between still defines a
            # box, so the final position is applied here.
            self.update_drag(event.position())
            self.drag_mode = None
            self.drag_start = None
            self.target_changed.emit(self.target)
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(LINE, 1))
        p.setBrush(PANEL)
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 12, 12)
        p.setPen(GREEN)
        p.setFont(QFont("Segoe UI", 10, QFont.Bold))
        p.drawText(20, 26, "DUVARDA İSABET")
        p.setPen(MUTED)
        p.setFont(QFont("Segoe UI", 8))
        p.drawText(20, 44, "Hedefi sürükle; köşe ve kenar tutamaklarıyla boyutlandır")
        p.setPen(QPen(LINE, 1))
        p.setBrush(QColor("#f6f8f3"))
        p.drawPolygon(self.wall_polygon())
        x0, y0, x1, y1 = self.target
        target = self.target_polygon()
        p.setPen(QPen(GREEN, 1, Qt.DashLine))
        p.setBrush(QColor("#e7edd1"))
        p.drawPolygon(target)
        corners, midpoints = self.handle_positions()
        p.setBrush(PANEL)
        p.setPen(QPen(GREEN, 2))
        for spot in corners:
            p.drawRect(QRectF(spot.x() - 4, spot.y() - 4, 8, 8))
        p.setPen(QPen(ORANGE, 2))
        for spot in midpoints:
            p.drawEllipse(spot, 3.5, 3.5)
        if self.session:
            for shot in self.session.shots:
                if not shot.included:
                    continue
                if shot.wall_xy is None:
                    continue
                x, y = shot.wall_xy
                point = self.wall_to_plot(shot.wall_xy)
                color = GREEN if x0 <= x <= x1 and y0 <= y <= y1 else ORANGE
                p.setBrush(color if shot.reviewed else PANEL)
                p.setPen(QPen(color, 2))
                p.drawEllipse(point, 6, 6)
        p.setPen(MUTED)
        p.setFont(QFont("Segoe UI", 8))
        p.drawText(20, self.height() - 15, "● Hedefte     ● Dışarıda     ○ İncelenmemiş aday")


class SpeedChart(QWidget):
    shot_clicked = Signal(str)

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(195)
        self.setMaximumHeight(205)
        self.session = None
        self.setMouseTracking(True)

    def entries(self):
        if not self.session:
            return []
        return [
            (
                shot,
                approach_speed_candidate(shot, self.session.calibration),
                approach_speed(shot, self.session.calibration),
            )
            for shot in self.session.shots
            if shot.included
        ]

    def chart_rect(self):
        return QRectF(42, 68, max(10, self.width() - 65), max(10, self.height() - 104))

    def entry_at(self, pos):
        entries = self.entries()
        r = self.chart_rect()
        if not entries or not r.contains(pos):
            return None
        index = min(len(entries) - 1, int((pos.x() - r.x()) / r.width() * len(entries)))
        return index, entries[index]

    def mouseMoveEvent(self, event):
        selected = self.entry_at(event.position())
        if selected is None:
            QToolTip.hideText()
            return
        index, (shot, candidate, reliable) = selected
        if reliable is not None:
            detail = f"{reliable:g} km/sa · güvenilir tahmin"
        elif candidate is not None:
            detail = f"≈{candidate:g} km/sa · düşük güven, zamanı incele"
        elif shot.wall_t is None:
            detail = "Duvar zamanı bulunamadı; hız hesaplanamaz"
        else:
            detail = "Ölçülen mesafe veya geçerli temas süresi gerekli"
        QToolTip.showText(event.globalPosition().toPoint(), f"{index + 1}. vuruş · {detail}", self)

    def mousePressEvent(self, event):
        selected = self.entry_at(event.position())
        if selected is not None:
            self.shot_clicked.emit(selected[1][0].id)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(LINE, 1))
        p.setBrush(PANEL)
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 12, 12)
        p.setPen(GREEN)
        p.setFont(QFont("Segoe UI", 10, QFont.Bold))
        p.drawText(20, 26, "VURUŞ BAZINDA YAKLAŞMA HIZI")
        p.setPen(MUTED)
        p.setFont(QFont("Segoe UI", 8))
        entries = self.entries()
        reliable_count = sum(reliable is not None for _, _, reliable in entries)
        provisional_count = sum(candidate is not None and reliable is None for _, candidate, reliable in entries)
        missing_count = len(entries) - reliable_count - provisional_count
        p.drawText(
            20,
            44,
            f"{len(entries)} vuruş · {reliable_count} güvenilir · {provisional_count} düşük güven · {missing_count} boş",
        )
        if not entries:
            p.setPen(MUTED)
            p.setFont(QFont("Segoe UI", 10))
            p.drawText(
                self.rect().adjusted(25, 52, -25, -30),
                Qt.AlignCenter | Qt.TextWordWrap,
                "Vuruşlar analiz edildiğinde hız durumları burada görünür.",
            )
            return
        r = self.chart_rect()
        values = [candidate for _, candidate, _ in entries if candidate is not None]
        ceiling = max(20, max(values) * 1.15) if values else 20
        p.setPen(QPen(LINE, 1))
        for ratio in (0, 0.5, 1):
            y = r.bottom() - ratio * r.height()
            p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
            p.drawText(QRectF(0, y - 8, 35, 18), Qt.AlignRight, str(round(ceiling * ratio)))
        width = r.width() / len(entries)
        for i, (_, candidate, reliable) in enumerate(entries):
            x = r.x() + (i + 0.5) * width
            if candidate is None:
                p.setPen(QPen(QColor("#aab7ad"), 2))
                p.drawLine(QPointF(x - min(4, width / 4), r.bottom() - 5), QPointF(x + min(4, width / 4), r.bottom() - 5))
            else:
                height = candidate / ceiling * r.height()
                p.setPen(Qt.NoPen)
                p.setBrush(GREEN if reliable is not None else ORANGE)
                p.drawRect(QRectF(x - max(1, width - 4) / 2, r.bottom() - height, max(1, width - 4), height))
        p.setPen(MUTED)
        p.setFont(QFont("Segoe UI", 8))
        p.drawText(20, self.height() - 15, "Yeşil: güvenilir · Turuncu: düşük güven · Çizgi: veri eksik")
