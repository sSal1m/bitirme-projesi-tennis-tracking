from __future__ import annotations

import argparse
import json
import os
import sys
from copy import deepcopy
from pathlib import Path
from threading import Event

from PySide6.QtCore import QRectF, QSize, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QImage, QPainter, QPen
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoFrame, QVideoSink
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSlider,
    QSplitter,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .analysis import AnalysisCancelled, analyze
from .domain import Calibration, Session, Shot, approach_speed, approach_speed_candidate
from .hardware import send_summary
from .rendering import export_video
from .storage import SessionStore, export_csv, export_json
from .video import frame_at, probe
from .widgets import LiveMetric, MetricCard, SpeedChart, VideoCanvas, WallChart, as_qimage

ROOT = Path(__file__).resolve().parents[1]
STYLE = """
QWidget { font-family: 'Segoe UI'; font-size: 12px; color: #233d30; }
QMainWindow, #main { background: #f3f5ef; }
#sidebar { background: #e5e9dc; border-right: 1px solid #d3dacb; }
#brand { font-size: 25px; font-weight: 800; color: #215b46; }
#title { font-size: 27px; font-weight: 700; }
#muted { color: #7b8679; font-size: 11px; }
#eyebrow { color: #466b50; font-size: 10px; font-weight: 700; letter-spacing: 1px; }
#metric { font-size: 34px; font-weight: 600; color: #1e4937; }
#card { background: #fffefb; border: 1px solid #dce4d8; border-radius: 12px; }
#overviewScroll { background: transparent; border: none; }
#sectionTitle { color: #1e4937; font-size: 16px; font-weight: 700; }
#sectionHint { color: #748377; font-size: 11px; }
#setupGroup { color: #426755; font-size: 11px; font-weight: 700; }
#videoToolbar { background: #fffefb; border-top: 1px solid #e3e9df; }
#timecode { font-family: Consolas; font-size: 12px; font-weight: 700; color: #315d49; }
#livePanel { background: #f2f6ec; border-top: 1px solid #dce4d8; }
#liveMetric { background: #fffefb; border: 1px solid #dce4d8; border-radius: 6px; }
#liveLabel { color: #5b7662; font-size: 9px; font-weight: 700; }
#liveValue { color: #1e4937; font-size: 19px; font-weight: 700; }
#notice { background: #e7edd1; border-radius: 6px; padding: 9px; color: #4a5b37; }
QPushButton { border: 1px solid #ccd5c4; background: #fffef8; border-radius: 6px; padding: 8px 12px; }
QPushButton:hover { background: #e8efd8; }
QPushButton:disabled { color: #9ba595; background: #edf0e7; }
QPushButton#primary { background: #215b46; color: #fffef2; border: none; font-weight: 700; }
QPushButton#primary:hover { background: #337359; }
QPushButton#primary:disabled { background: #94aa99; }
QLineEdit, QComboBox, QDoubleSpinBox { background: #fffef8; border: 1px solid #ccd5c4; padding: 5px; border-radius: 4px; }
QListWidget { background: transparent; border: none; outline: 0; }
QListWidget::item { padding: 12px 5px; border-bottom: 1px solid #d3dacb; }
QListWidget::item:selected { background: #d3dec8; color: #214c37; border-radius: 5px; }
QTabWidget::pane { border: none; }
QTabBar::tab { padding: 10px 20px; background: transparent; color: #71816e; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: #215b46; border-bottom: 2px solid #215b46; font-weight: bold; }
QTableWidget { background: #fffef8; border: 1px solid #d5ddcd; gridline-color: #e5e9dd; }
QHeaderView::section { background: #e5e9dc; padding: 8px; border: none; font-weight: 600; }
QProgressBar { border: none; background: #dce3d3; border-radius: 3px; height: 6px; }
QProgressBar::chunk { background: #548267; border-radius: 3px; }
QSlider::groove:horizontal { height: 4px; background: #d0d8c6; }
QSlider::handle:horizontal { width: 12px; margin: -4px 0; border-radius: 6px; background: #215b46; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { width: 8px; background: transparent; margin: 2px; }
QScrollBar::handle:vertical { background: #c6d4c6; border-radius: 4px; min-height: 28px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
"""


class Worker(QThread):
    progress = Signal(int, str)
    done = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, action, parent=None):
        super().__init__(parent)
        self.action = action
        self.stop = Event()

    def run(self):
        try:
            result = self.action(self.progress.emit, self.stop.is_set)
            self.done.emit(result)
        except AnalysisCancelled:
            self.cancelled.emit()
        except Exception as exc:
            self.failed.emit(str(exc))


class HelpHeader(QHeaderView):
    help_columns = {1, 2, 5}

    def paintSection(self, painter, rect, logical_index):
        super().paintSection(painter, rect, logical_index)
        if logical_index not in self.help_columns:
            return
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        center = rect.center()
        circle = QRectF(rect.right() - 22, center.y() - 6, 12, 12)
        painter.setPen(QPen(QColor("#426755"), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(circle)
        painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
        painter.drawText(circle, Qt.AlignCenter, "i")
        painter.restore()


def button(text, handler, primary=False):
    b = QPushButton(text)
    if primary:
        b.setObjectName("primary")
    b.clicked.connect(handler)
    return b


def spin(maximum=36000, decimals=3):
    result = QDoubleSpinBox()
    result.setRange(0, maximum)
    result.setDecimals(decimals)
    result.setSingleStep(0.01)
    return result


class MainWindow(QMainWindow):
    def __init__(self, data_dir=None):
        super().__init__()
        self.setWindowTitle("Duvar Tenis · Antrenman Laboratuvarı")
        self.resize(1420, 960)
        self.setMinimumSize(1060, 760)
        self.store = SessionStore(data_dir or ROOT / "data")
        self.session = None
        self.worker = None
        self.video_path = None
        self.model_path = None
        self.wall_capture = False
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(0.5)
        self.player.setAudioOutput(self.audio)
        self.sink = QVideoSink(self)
        self.player.setVideoSink(self.sink)
        self._build()
        self.sink.videoFrameChanged.connect(self.video_frame)
        self.player.positionChanged.connect(self.position_changed)
        self.player.durationChanged.connect(lambda ms: self.timeline.setMaximum(ms))
        self.player.playbackStateChanged.connect(self.update_play_icon)
        self.player.errorOccurred.connect(lambda error, msg: self.notify("Video oynatma: " + msg))
        self.refresh_history()

    def _build(self):
        root = QWidget()
        root.setObjectName("main")
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(210)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(18, 28, 18, 22)
        brand = QLabel("DUVAR")
        brand.setObjectName("brand")
        side.addWidget(brand)
        sub = QLabel("TENİS ANTRENMAN LABORATUVARI")
        sub.setObjectName("eyebrow")
        sub.setWordWrap(True)
        side.addWidget(sub)
        side.addSpacing(25)
        self.upload_btn = button("+  Video yükle", self.open_video, True)
        side.addWidget(self.upload_btn)
        self.demo_btn = button("Örnek oturumu keşfet", self.load_demo)
        side.addWidget(self.demo_btn)
        side.addSpacing(20)
        side.addWidget(QLabel("ANTRENMAN GEÇMİŞİ"))
        self.history = QListWidget()
        self.history.itemClicked.connect(self.load_history)
        self.history.currentItemChanged.connect(self.update_delete_history_button)
        side.addWidget(self.history, 1)
        self.delete_history_btn = button("Seçili antrenmanı sil", self.delete_history)
        self.delete_history_btn.setEnabled(False)
        self.delete_history_btn.setToolTip("Analiz kaydını geçmişten kaldırır; kaynak video korunur.")
        side.addWidget(self.delete_history_btn)
        footer = QLabel("●  Yerel çalışma\nVideolar bu bilgisayarda kalır.\n\nv0.1 · Ölç, incele, geliştir.")
        footer.setObjectName("muted")
        side.addWidget(footer)
        outer.addWidget(sidebar)
        content = QVBoxLayout()
        content.setContentsMargins(26, 24, 26, 20)
        outer.addLayout(content, 1)
        header = QHBoxLayout()
        heading = QVBoxLayout()
        label = QLabel("OYUNUNU YAKINDAN TANI")
        label.setObjectName("eyebrow")
        heading.addWidget(label)
        self.title = QLabel("Bir duvar. Daha iyi bir oyun.")
        self.title.setObjectName("title")
        heading.addWidget(self.title)
        header.addLayout(heading, 1)
        self.export_btn = button("Dışa aktar ↗", self.export_results)
        header.addWidget(self.export_btn)
        content.addLayout(header)
        self.tabs = QTabWidget()
        content.addWidget(self.tabs, 1)
        self.overview_scroll = QScrollArea()
        self.overview_scroll.setObjectName("overviewScroll")
        self.overview_scroll.setWidgetResizable(True)
        self.overview_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        overview = QWidget()
        main = QVBoxLayout(overview)
        main.setContentsMargins(0, 12, 12, 6)
        main.setSpacing(12)
        top = QSplitter(Qt.Horizontal)
        top.setHandleWidth(12)
        viewer = QFrame()
        viewer.setObjectName("card")
        vl = QVBoxLayout(viewer)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)
        video_heading = QWidget()
        video_heading.setObjectName("videoToolbar")
        video_heading_layout = QHBoxLayout(video_heading)
        video_heading_layout.setContentsMargins(16, 10, 16, 10)
        video_heading_layout.addWidget(QLabel("VİDEO İNCELEME", objectName="eyebrow"))
        video_heading_layout.addStretch()
        video_heading_layout.addWidget(QLabel("Kare kare kontrol", objectName="sectionHint"))
        vl.addWidget(video_heading)
        self.canvas = VideoCanvas()
        self.canvas.point_clicked.connect(self.canvas_clicked)
        vl.addWidget(self.canvas, 1)
        control_bar = QWidget()
        control_bar.setObjectName("videoToolbar")
        controls = QHBoxLayout(control_bar)
        controls.setContentsMargins(10, 9, 10, 9)
        controls.setSpacing(8)
        self.play_btn = button("", self.toggle_play)
        self.play_btn.setIconSize(QSize(20, 20))
        self.update_play_icon(self.player.playbackState())
        controls.addWidget(self.play_btn)
        previous_frame = button("−1", lambda: self.step(-1))
        previous_frame.setToolTip("Önceki kare")
        previous_frame.setFixedWidth(48)
        controls.addWidget(previous_frame)
        next_frame = button("+1", lambda: self.step(1))
        next_frame.setToolTip("Sonraki kare")
        next_frame.setFixedWidth(48)
        controls.addWidget(next_frame)
        self.timeline = QSlider(Qt.Horizontal)
        self.timeline.sliderMoved.connect(self.seek)
        controls.addWidget(self.timeline, 1)
        self.time_label = QLabel("00:00.000")
        self.time_label.setObjectName("timecode")
        controls.addWidget(self.time_label)
        vl.addWidget(control_bar)
        live_panel = QFrame()
        live_panel.setObjectName("livePanel")
        live_layout = QVBoxLayout(live_panel)
        live_layout.setContentsMargins(12, 7, 12, 9)
        live_layout.setSpacing(5)
        live_layout.addWidget(QLabel("VİDEONUN BU ANINA KADAR", objectName="eyebrow"))
        live_row = QHBoxLayout()
        live_row.setSpacing(6)
        self.live_cards = [
            LiveMetric("VURUŞ", "Bu ana kadar başlayan vuruşlar"),
            LiveMetric("FH - BH", "Bu ana kadar forehand ve backhand sayıları"),
            LiveMetric("HEDEF", "Bu ana kadar duvara ulaşan, konumu belirlenen vuruşların isabeti"),
            LiveMetric("HIZ", "Bu ana kadar tamamlanan güvenilir uçuşların ortalama yaklaşma hızı"),
        ]
        for card in self.live_cards:
            live_row.addWidget(card, 1)
        live_layout.addLayout(live_row)
        vl.addWidget(live_panel)
        top.addWidget(viewer)
        self.setup_container = QFrame()
        self.setup_container.setObjectName("card")
        self.setup_container.setMinimumWidth(325)
        self.setup_container.setMaximumWidth(370)
        setup_container_layout = QVBoxLayout(self.setup_container)
        setup_container_layout.setContentsMargins(0, 0, 0, 0)
        setup_container_layout.setSpacing(0)
        self.setup_scroll = QScrollArea()
        self.setup_scroll.setFrameShape(QFrame.NoFrame)
        self.setup_scroll.setWidgetResizable(True)
        self.setup_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setup_scroll.viewport().setStyleSheet("background: #fffefb;")
        self.setup_panel = QFrame()
        setup = QVBoxLayout(self.setup_panel)
        setup.setContentsMargins(14, 17, 14, 18)
        setup.setSpacing(9)
        step_label = QLabel("ANTRENMAN AYARLARI")
        step_label.setObjectName("sectionTitle")
        setup.addWidget(step_label)
        setup_intro = QLabel("Çekim bilgilerini gir ve duvarı işaretle.")
        setup_intro.setObjectName("sectionHint")
        setup_intro.setWordWrap(True)
        setup.addWidget(setup_intro)
        setup.addSpacing(7)
        setup.addWidget(QLabel("01  ÇEKİM", objectName="setupGroup"))
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        form.setVerticalSpacing(10)
        self.name = QLineEdit()
        self.name.setPlaceholderText("Antrenman adı")
        form.addRow("Ad", self.name)
        self.hand = QComboBox()
        self.hand.addItems(["Sağ el", "Sol el"])
        form.addRow("Raket eli", self.hand)
        self.mirrored = QCheckBox("Video aynalanmış")
        form.addRow(self.mirrored)
        setup.addLayout(form)
        setup.addSpacing(8)
        setup.addWidget(QLabel("02  ÖLÇÜM VE TAKİP", objectName="setupGroup"))
        measure_form = QFormLayout()
        measure_form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        measure_form.setVerticalSpacing(10)
        self.distance = spin(30, 2)
        self.distance.setSpecialValueText("Girilmedi")
        self.distance.setSuffix(" m")
        measure_form.addRow("Temas–duvar", self.distance)
        self.fixed_plane = QCheckBox("Sabit mesafeyi ölçtüm")
        self.fixed_plane.setToolTip("Raket temas noktası ile duvar arasındaki dik mesafeyi ölçtüm.")
        measure_form.addRow(self.fixed_plane)
        self.detector = QComboBox()
        self.detector.addItems(["Renk / hareket · deneysel", "RF-DETR · özel model"])
        self.detector.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.detector.setMinimumContentsLength(10)
        measure_form.addRow("Top takibi", self.detector)
        setup.addLayout(measure_form)
        setup.addWidget(button("Mesafeyi oturuma uygula", self.apply_distance))
        setup.addWidget(button("RF-DETR modeli seç…", self.choose_model))
        setup.addSpacing(8)
        setup.addWidget(QLabel("03  DUVAR KALİBRASYONU", objectName="setupGroup"))
        setup.addWidget(button("Duvarın 4 köşesini seç", self.start_calibration))
        self.calibration_hint = QLabel("Sol üst → sağ üst → sağ alt → sol alt")
        self.calibration_hint.setWordWrap(True)
        self.calibration_hint.setObjectName("muted")
        setup.addWidget(self.calibration_hint)
        setup.addStretch()
        for widget in self.setup_panel.findChildren(QPushButton):
            widget.setMinimumHeight(34)
        for widget in (self.name, self.hand, self.distance, self.detector):
            widget.setMinimumHeight(30)
        self.setup_panel.setMinimumHeight(setup.sizeHint().height())
        self.setup_scroll.setWidget(self.setup_panel)
        setup_container_layout.addWidget(self.setup_scroll, 1)
        action_row = QHBoxLayout()
        action_row.setContentsMargins(18, 10, 18, 16)
        self.analyze_btn = button("Antrenmanı analiz et →", self.start_analysis, True)
        self.analyze_btn.setMinimumHeight(42)
        action_row.addWidget(self.analyze_btn)
        setup_container_layout.addLayout(action_row)
        top.addWidget(self.setup_container)
        top.setStretchFactor(0, 1)
        top.setStretchFactor(1, 0)
        top.setSizes([790, 340])
        top_frame = QWidget()
        top_frame_layout = QVBoxLayout(top_frame)
        top_frame_layout.setContentsMargins(0, 0, 0, 0)
        top_frame_layout.addWidget(top)
        top_frame.setFixedHeight(470)
        main.addWidget(top_frame)
        metrics = QHBoxLayout()
        metrics.setSpacing(12)
        self.cards = [
            MetricCard("VURUŞ", "İnceleme bekleyen adaylar"),
            MetricCard("FOREHAND - BACKHAND", "Belirsizler ayrıca gösterilir"),
            MetricCard("TAHMİNİ HEDEF İSABETİ", "Konumu belirlenen temaslar"),
            MetricCard("YAKLAŞMA HIZI", "Tahmin · km/sa"),
        ]
        for card in self.cards:
            metrics.addWidget(card)
        main.addLayout(metrics)
        charts = QHBoxLayout()
        charts.setSpacing(12)
        self.wall_chart = WallChart()
        self.wall_chart.target_changed.connect(self.change_target)
        self.wall_chart.shot_clicked.connect(self.show_wall_shot)
        self.speed_chart = SpeedChart()
        self.speed_chart.shot_clicked.connect(self.show_speed_shot)
        charts.addWidget(self.wall_chart, 1)
        charts.addWidget(self.speed_chart, 1)
        main.addLayout(charts)
        main.addStretch(1)
        overview.setMinimumHeight(810)
        self.overview_scroll.setWidget(overview)
        self.tabs.addTab(self.overview_scroll, "Antrenman")
        self._build_review()
        self._build_history_tab()
        self._build_device_tab()
        self.notice = QLabel(
            "Başlamak için bir video yükle. Örnek oturum sentetik verilerle arayüzü gösterir."
        )
        self.notice.setObjectName("notice")
        self.notice.setWordWrap(True)
        content.addWidget(self.notice)
        progress_row = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.hide()
        self.cancel_btn = button("İptal", self.cancel_work)
        self.cancel_btn.hide()
        progress_row.addWidget(self.progress, 1)
        progress_row.addWidget(self.cancel_btn)
        content.addLayout(progress_row)

    def _build_review(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        hint = QLabel(
            "Bir vuruş seç → zamanını ve türünü düzelt → kaydet. Yeni vuruş için raket ve duvar temas anlarını işaretle."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.shot_table = QTableWidget(0, 7)
        self.shot_table.setHorizontalHeader(HelpHeader(Qt.Horizontal, self.shot_table))
        self.shot_table.setHorizontalHeaderLabels(
            ["#", "Raket (sn)", "Duvar (sn)", "Tür", "Hız tahmini", "Kaynak", "Durum"]
        )
        header_help = {
            1: ("Raket (sn)", "Topun rakete temas ettiği an; videonun başlangıcından itibaren saniye."),
            2: ("Duvar (sn)", "Topun duvara temas ettiği an; bulunamadıysa — gösterilir."),
            5: (
                "Kaynak",
                "Otomatik: sistem tespit etti. Elle: vuruşu sen ekledin. Kontrol edildiğini Durum sütunu gösterir.",
            ),
        }
        for column, (title, explanation) in header_help.items():
            item = self.shot_table.horizontalHeaderItem(column)
            item.setText(title)
            item.setToolTip(explanation)
        self.shot_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.shot_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.shot_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.shot_table.itemSelectionChanged.connect(self.select_shot)
        self.shot_table.cellDoubleClicked.connect(lambda row, col: self.jump_to_shot(row))
        layout.addWidget(self.shot_table, 1)
        edit = QHBoxLayout()
        self.contact_time = spin()
        self.wall_time = spin()
        self.wall_time.setSpecialValueText("Belirlenmedi")
        self.kind = QComboBox()
        self.kind.addItems(["Belirsiz", "Forehand", "Backhand"])
        for label, widget in [
            ("Raket sn", self.contact_time),
            ("Duvar sn", self.wall_time),
            ("Tür", self.kind),
        ]:
            edit.addWidget(QLabel(label))
            edit.addWidget(widget)
        layout.addLayout(edit)
        buttons = QHBoxLayout()
        buttons.addWidget(button("Yeni / mevcut anı al", self.new_shot))
        buttons.addWidget(button("Duvar anını al", self.capture_wall_time))
        buttons.addWidget(button("Duvardaki noktayı seç", self.pick_wall_point))
        buttons.addWidget(button("İncelendi · kaydet", self.save_shot, True))
        buttons.addWidget(button("Dahil et / çıkar", self.toggle_shot))
        layout.addLayout(buttons)
        self.point_label = QLabel("Duvar noktası: belirlenmedi")
        layout.addWidget(self.point_label)
        self.edit_wall_xy = None
        self.edit_id = None
        self.tabs.addTab(tab, "Vuruş inceleme")

    def _build_history_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        text = QLabel(
            "Karşılaştırmaları aynı çekim düzeni ve aynı hedef boyutuyla yap. Otomatik sonuçları incelemeden gelişim sonucu çıkarma."
        )
        text.setWordWrap(True)
        layout.addWidget(text)
        self.comparison = QTableWidget(0, 8)
        self.comparison.setHorizontalHeaderLabels(
            ["Antrenman", "Tarih", "Vuruş", "Hedef %", "İncelenen", "Konumsuz", "Aralık sn", "Dağılım*"]
        )
        self.comparison.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.comparison.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.comparison)
        layout.addWidget(
            QLabel("* Normalize duvar koordinatlarında RMS yayılımı; küçük değer daha toplu isabet demektir.")
        )
        self.tabs.addTab(tab, "Gelişim")

    def _build_device_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        text = QLabel(
            "MASADAKİ SKOR EKRANIN\n\nESP32 + SSD1306 OLED\nUSB üzerinden seçili antrenmanın özetini gösterir.\nSensör ve internet bağlantısı gerektirmez."
        )
        text.setFont(QFont("Segoe UI", 16))
        layout.addWidget(text)
        row = QHBoxLayout()
        self.ports = QComboBox()
        row.addWidget(self.ports)
        row.addWidget(button("Portları yenile", self.refresh_ports))
        row.addWidget(button("Sonuçları ekrana gönder", self.send_device, True))
        row.addStretch()
        layout.addLayout(row)
        self.device_preview = QLabel("Henüz analiz yok.")
        self.device_preview.setStyleSheet(
            "background:#143d30;color:#dce895;padding:30px;font-family:Consolas;font-size:20px;"
        )
        layout.addWidget(self.device_preview)
        help_text = QLabel(
            "Bağlantı ve yükleme adımları: docs/DONANIM.md\nKart takılı değilken yazılımın bütün analiz işlevleri kullanılabilir."
        )
        layout.addWidget(help_text)
        layout.addStretch()
        self.tabs.addTab(tab, "Donanım ekranı")
        self.refresh_ports()

    def notify(self, text):
        self.notice.setText(text)

    def error(self, text):
        self.notify(text)
        QMessageBox.warning(self, "İşlem tamamlanamadı", text)

    def is_busy(self):
        return self.worker is not None and self.worker.isRunning()

    def open_video(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Antrenman videosu", "", "Videolar (*.mp4 *.mov *.mkv *.avi)"
        )
        if path:
            self.load_video(path)

    def load_video(self, path):
        if self.is_busy():
            return
        try:
            info = probe(path)
            first = frame_at(path, 0)
        except Exception as exc:
            self.error(str(exc))
            return
        self.player.stop()
        self.video_path = str(Path(path).resolve())
        self.session = Session(
            video_path=self.video_path,
            calibration=Calibration(),
            name=Path(path).stem,
            duration=info.duration,
            fps=info.fps,
            width=info.width,
            height=info.height,
        )
        self.canvas.points = []
        self.canvas.mode = "view"
        self.canvas.set_session(self.session)
        self.canvas.set_image(as_qimage(first))
        self.player.setSource(QUrl.fromLocalFile(self.video_path))
        self.name.setText(self.session.name)
        self.distance.setValue(0)
        self.fixed_plane.setChecked(False)
        self.wall_chart.target = self.session.calibration.target
        self.title.setText("Antrenmanını keşfet.")
        self.tabs.setCurrentIndex(0)
        self.new_shot()
        self.refresh_results()
        self.notify(
            f"{info.width} × {info.height} · {info.fps:.1f} FPS · {info.duration:.1f} sn. Önce duvarın dört köşesini seç."
        )

    def load_demo(self):
        if self.is_busy():
            return
        from .demo import create_demo

        self.notify("Sentetik örnek oturum hazırlanıyor…")
        QApplication.processEvents()
        try:
            session = create_demo(self.store.root / "demo")
            self.store.save(session)
            self.open_session(session)
        except Exception as exc:
            self.error(str(exc))

    def open_session(self, session):
        self.load_video(session.video_path)
        if self.video_path != session.video_path:
            return
        self.session = session
        self.canvas.points = deepcopy(session.calibration.wall)
        self.canvas.set_session(session)
        self.wall_chart.target = session.calibration.target
        self.distance.setValue(session.calibration.distance_m or 0)
        self.fixed_plane.setChecked(session.calibration.fixed_contact_plane)
        self.hand.setCurrentIndex(session.calibration.handedness == "left")
        self.mirrored.setChecked(session.calibration.mirrored)
        self.detector.setCurrentIndex(session.detector == "rfdetr")
        self.name.setText(session.name)
        self.title.setText(session.name)
        self.refresh_results()
        self.notify(" · ".join(session.warnings) or "Oturum yüklendi.")

    def video_frame(self, frame):
        # toImage() alone ignores display rotations in phone videos. Qt's painter
        # applies the surface and presentation transforms consistently.
        if not frame.isValid():
            return
        if self.session and self.session.width and self.session.height:
            image = QImage(self.session.width, self.session.height, QImage.Format_RGB32)
            image.fill(Qt.black)
            painter = QPainter(image)
            frame.paint(painter, QRectF(0, 0, image.width(), image.height()), QVideoFrame.PaintOptions())
            painter.end()
        else:
            image = frame.toImage()
        if not image.isNull():
            self.canvas.set_image(image)

    def position_changed(self, ms):
        if not self.timeline.isSliderDown():
            self.timeline.setValue(ms)
        self.canvas.t = ms / 1000
        self.canvas.update()
        self.time_label.setText(f"{ms // 60000:02d}:{(ms // 1000) % 60:02d}.{ms % 1000:03d}")
        self.refresh_live_metrics(ms / 1000)

    def seek(self, ms):
        self.player.setPosition(ms)

    def step(self, direction):
        if not self.session:
            return
        self.player.pause()
        value = max(
            0,
            min(self.player.duration(), self.player.position() + round(direction * 1000 / self.session.fps)),
        )
        self.player.setPosition(value)
        try:
            self.canvas.set_image(as_qimage(frame_at(self.video_path, value / 1000)))
        except Exception as exc:
            self.notify(str(exc))

    def toggle_play(self):
        if not self.video_path:
            return
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.canvas.mode = "view"
            self.player.play()

    def update_play_icon(self, state):
        playing = state == QMediaPlayer.PlayingState
        self.play_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPause if playing else QStyle.SP_MediaPlay))
        label = "Duraklat" if playing else "Oynat"
        self.play_btn.setToolTip(label)
        self.play_btn.setAccessibleName(label)

    def choose_model(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Duvar verisiyle eğitilmiş RF-DETR Nano", "", "Model (*.pth)"
        )
        if path:
            self.model_path = path
            self.detector.setCurrentIndex(1)
            self.notify("Model seçildi: " + Path(path).name)

    def start_calibration(self):
        if not self.video_path:
            self.notify("Önce bir video yükle.")
            return
        self.player.pause()
        self.canvas.mode = "calibrate"
        self.canvas.points = []
        self.wall_capture = False
        self.canvas.update()
        self.notify("Duvar üzerinde dikdörtgen bir alan seç: sol üst → sağ üst → sağ alt → sol alt.")

    def canvas_clicked(self, x, y):
        if self.is_busy():
            return
        if self.wall_capture and self.session:
            try:
                xy = self.session.calibration.wall_point([x, y])
                if not all(0 <= v <= 1 for v in xy):
                    raise ValueError("Seçilen nokta kalibre edilmiş duvar alanının dışında.")
                self.edit_wall_xy = xy
                self.point_label.setText(f"Duvar noktası: x={xy[0]:.3f}, y={xy[1]:.3f}")
                self.wall_capture = False
                self.tabs.setCurrentIndex(1)
            except ValueError as exc:
                self.notify(str(exc))
            return
        if self.canvas.mode == "calibrate" and len(self.canvas.points) < 4:
            self.canvas.points.append([x, y])
            self.canvas.update()
            self.calibration_hint.setText(f"{len(self.canvas.points)} / 4 köşe seçildi")
            if len(self.canvas.points) == 4:
                try:
                    self.current_calibration().validate()
                    self.session.calibration = self.current_calibration()
                    # Old automatic geometry is no longer trustworthy after re-calibration.
                    if self.session.shots:
                        for shot in self.session.shots:
                            shot.wall_xy = None
                        self.notify(
                            "Kalibrasyon değişti. Eski duvar noktaları temizlendi; yeniden analiz et veya işaretle."
                        )
                    else:
                        self.notify(
                            "Duvar hazır. Alt haritada hedefi sürükleyerek seçebilir, analizi başlatabilirsin."
                        )
                    self.canvas.mode = "view"
                    self.refresh_results()
                except ValueError as exc:
                    self.canvas.points = []
                    self.notify(str(exc))

    def current_calibration(self):
        return Calibration(
            wall=deepcopy(self.canvas.points),
            target=list(self.wall_chart.target),
            distance_m=self.distance.value() or None,
            fixed_contact_plane=self.fixed_plane.isChecked(),
            handedness="right" if self.hand.currentIndex() == 0 else "left",
            mirrored=self.mirrored.isChecked(),
        )

    def apply_distance(self):
        if not self.session or self.session.status != "complete":
            self.notify("Önce bir antrenmanı analiz et veya geçmişten aç.")
            return
        distance = self.distance.value()
        if not self.fixed_plane.isChecked() or distance < 0.2:
            self.notify(
                "Hız için raket temas düzlemi–duvar mesafesini metre cinsinden ölç, gir ve kutuyu işaretle."
            )
            return
        self.session.calibration.distance_m = distance
        self.session.calibration.fixed_contact_plane = True
        self.persist()
        self.refresh_results()
        included = [shot for shot in self.session.shots if shot.included]
        reliable = sum(approach_speed(shot, self.session.calibration) is not None for shot in included)
        timed = sum(
            approach_speed_candidate(shot, self.session.calibration) is not None for shot in included
        )
        self.notify(
            f"Mesafe kaydedildi: {len(included)} vuruşun {reliable} tanesinde güvenilir, "
            f"{timed - reliable} tanesinde düşük güvenli hız tahmini var; "
            f"{len(included) - timed} tanesinde geçerli duvar zamanı yok. Eksikleri Vuruş inceleme bölümünde tamamlayabilirsin."
        )

    def start_analysis(self):
        if not self.session or self.is_busy():
            return
        try:
            calibration = self.current_calibration()
            calibration.validate()
        except ValueError as exc:
            self.error(str(exc))
            return
        if self.detector.currentIndex() == 1 and not self.model_path:
            self.error("Önce eğitilmiş RF-DETR modelini seç. Renk modu model dosyası olmadan çalışır.")
            return
        self.player.pause()
        # Re-analysis creates a new session so reviewed results are not overwritten.
        session = Session(
            video_path=self.video_path,
            calibration=calibration,
            name=self.name.text().strip() or Path(self.video_path).stem,
            detector="color" if self.detector.currentIndex() == 0 else "rfdetr",
        )
        pose = ROOT / "models" / "pose_landmarker_lite.task"
        self.run_work(
            lambda progress, stop: analyze(session, self.model_path, str(pose), progress, stop),
            self.analysis_done,
        )

    def run_work(self, action, callback):
        if self.is_busy():
            return
        self.worker = Worker(action, self)
        self.worker.progress.connect(
            lambda value, message: (self.progress.setValue(value), self.notify(message))
        )
        self.worker.done.connect(callback)
        self.worker.failed.connect(self.error)
        self.worker.cancelled.connect(lambda: self.notify("İşlem iptal edildi; önceki oturum korundu."))
        self.worker.finished.connect(self.work_finished)
        self.progress.setValue(0)
        self.progress.show()
        self.cancel_btn.show()
        self.tabs.setEnabled(False)
        for widget in (self.upload_btn, self.demo_btn, self.export_btn, self.history):
            widget.setEnabled(False)
        self.delete_history_btn.setEnabled(False)
        self.worker.start()

    def work_finished(self):
        self.progress.hide()
        self.cancel_btn.hide()
        self.tabs.setEnabled(True)
        for widget in (self.upload_btn, self.demo_btn, self.export_btn, self.history):
            widget.setEnabled(True)
        if self.worker:
            self.worker.deleteLater()
        self.worker = None
        self.update_delete_history_button()

    def cancel_work(self):
        if self.worker:
            self.worker.stop.set()
            self.notify("İptal ediliyor…")

    def analysis_done(self, session):
        self.session = session
        self.fixed_plane.setChecked(session.calibration.fixed_contact_plane)
        self.canvas.set_session(session)
        self.title.setText(session.name)
        self.persist()
        self.refresh_results()
        self.notify(" · ".join(session.warnings) or "Analiz tamamlandı. Vuruşları inceleyebilirsin.")

    def persist(self):
        if self.session:
            try:
                self.store.save(self.session)
                self.refresh_history()
            except Exception as exc:
                self.error("Oturum kaydedilemedi: " + str(exc))

    def refresh_live_metrics(self, t):
        if not self.session:
            return
        current = self.session.summary_at(t)
        values = [
            str(current["strokes"]),
            f"{current['forehand']} - {current['backhand']}",
            f"%{current['hit_rate']:g}" if current["hit_rate"] is not None else "—",
            f"{current['approach_kmh']:g}" if current["approach_kmh"] is not None else "—",
        ]
        for card, value in zip(self.live_cards, values):
            card.value.setText(value)
        self.live_cards[2].setToolTip(
            f"Bu ana kadar {current['hits']}/{current['localized']} konumu belirlenen vuruş hedefte."
        )
        self.live_cards[3].setToolTip(
            f"Bu ana kadar {current['speed_count']} vuruşun güvenilir yaklaşma hızı; km/sa."
        )

    def refresh_results(self):
        if not self.session:
            return
        s = self.session.summary()
        for card, value in zip(
            self.cards,
            [
                s["strokes"],
                f"{s['forehand']} - {s['backhand']}",
                f"%{s['hit_rate']:g}" if s["hit_rate"] is not None else "—",
                f"{s['approach_kmh']:g}" if s["approach_kmh"] is not None else "—",
            ],
        ):
            card.value.setText(str(value))
        self.cards[0].hint.setText(f"{s['reviewed']} incelendi · {s['strokes'] - s['reviewed']} aday")
        self.cards[1].hint.setText(f"{s['unknown']} belirsiz vuruş")
        placement_note = (
            "Kamera kayması · " if any("kamera kayması" in w.lower() for w in self.session.warnings) else ""
        )
        self.cards[2].hint.setText(
            f"{placement_note}{s['hits']}/{s['localized']} konumlu isabet · {s['unlocalized']} konumsuz"
            if s["localized"]
            else "Duvar teması bulunamadı"
        )
        if self.session.calibration.distance_m is None:
            speed_hint = "Hız için ölçülen mesafeyi gir"
        elif not self.session.calibration.fixed_contact_plane:
            speed_hint = "Ölçülen mesafeyi doğrula"
        elif s["approach_kmh"] is None:
            speed_hint = "Duvar ve raket zamanlarını incele"
        else:
            speed_hint = "Duvara dik ortalama · km/sa"
        def speed_text(value):
            return f"{value:g} km/sa" if value is not None else "—"

        self.cards[3].hint.setText(
            f"{speed_hint}\n"
            f"Peak: {speed_text(s['peak_kmh'])}\n"
            f"Forehand: {speed_text(s['forehand_kmh'])}\n"
            f"Backhand: {speed_text(s['backhand_kmh'])}"
        )
        self.wall_chart.session = self.session
        self.speed_chart.session = self.session
        self.wall_chart.update()
        self.speed_chart.update()
        self.canvas.set_session(self.session)
        self.refresh_live_metrics(self.player.position() / 1000)
        self.shot_table.blockSignals(True)
        self.shot_table.setRowCount(len(self.session.shots))
        for row, shot in enumerate(self.session.shots):
            reliable_speed = approach_speed(shot, self.session.calibration)
            candidate_speed = approach_speed_candidate(shot, self.session.calibration)
            values = [
                str(row + 1),
                f"{shot.contact_t:.3f}",
                f"{shot.wall_t:.3f}" if shot.wall_t is not None else "—",
                {"unknown": "Belirsiz", "forehand": "Forehand", "backhand": "Backhand"}[shot.kind],
                (
                    f"{reliable_speed:g}"
                    if reliable_speed is not None
                    else f"≈{candidate_speed:g}" if candidate_speed is not None else "—"
                ),
                "Elle" if shot.source == "manual" else "Otomatik",
                "Hariç" if not shot.included else "İncelendi" if shot.reviewed else "Aday",
            ]
            for col, val in enumerate(values):
                self.shot_table.setItem(row, col, QTableWidgetItem(val))
            self.shot_table.item(row, 4).setToolTip(
                "Raket–duvar zamanı ve ölçülen mesafeden hesaplandı; radar hızı değildir."
                if reliable_speed is not None
                else "Düşük güvenli eşleşmeden hesaplandı; raket ve duvar anlarını incele."
                if candidate_speed is not None
                else "Duvar zamanı bulunamadı veya ölçülen mesafe/geçerli süre eksik; hız hesaplanamaz."
            )
        self.shot_table.blockSignals(False)
        hit = f"{s['hit_rate']:g}%" if s["hit_rate"] is not None else "--"
        speed = f"{s['approach_kmh']:g}" if s["approach_kmh"] is not None else "--"
        self.device_preview.setText(
            f"DUVAR TENIS\nVurus {s['strokes']}   FH {s['forehand']} / BH {s['backhand']}\nHedef {hit}   Tahmin {speed} km/h\nIncelenen {s['reviewed']}/{s['strokes']}"
        )

    def refresh_history(self):
        rows = self.store.list()
        selected = self.history.currentItem()
        selected_id = selected.data(Qt.UserRole) if selected else None
        self.history.clear()
        self.comparison.setRowCount(len(rows))
        for row, item in enumerate(rows):
            summary = json.loads(item["summary"])
            entry = QListWidgetItem(f"{item['name']}\n{item['created_at'][:10]} · {summary['strokes']} vuruş")
            entry.setData(Qt.UserRole, item["id"])
            self.history.addItem(entry)
            if item["id"] == selected_id:
                self.history.setCurrentItem(entry)
            vals = [
                item["name"],
                item["created_at"][:10],
                summary["strokes"],
                summary["hit_rate"] if summary["hit_rate"] is not None else "—",
                summary["reviewed"],
                summary["unlocalized"],
                summary.get("mean_interval_s") if summary.get("mean_interval_s") is not None else "—",
                summary.get("placement_spread") if summary.get("placement_spread") is not None else "—",
            ]
            for col, value in enumerate(vals):
                self.comparison.setItem(row, col, QTableWidgetItem(str(value)))

    def update_delete_history_button(self, *args):
        self.delete_history_btn.setEnabled(self.history.currentItem() is not None and not self.is_busy())

    def delete_history(self):
        item = self.history.currentItem()
        if item is None or self.is_busy():
            return
        session_id = item.data(Qt.UserRole)
        answer = QMessageBox.question(
            self,
            "Antrenmanı sil",
            f"{item.text().splitlines()[0]} antrenmanının analiz kaydı silinsin mi?\n\n"
            "Bu işlem geri alınamaz. Kaynak video dosyası korunur.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            self.store.delete(session_id)
        except Exception as exc:
            self.error("Antrenman silinemedi: " + str(exc))
            return
        if self.session and self.session.id == session_id:
            self.clear_session()
        self.refresh_history()
        self.notify("Antrenman geçmişten silindi. Kaynak video dosyası korundu.")

    def clear_session(self):
        self.player.stop()
        self.player.setSource(QUrl())
        self.session = None
        self.video_path = None
        self.canvas.set_session(None)
        self.canvas.set_image(QImage())
        self.canvas.points = []
        self.canvas.mode = "view"
        self.wall_capture = False
        self.timeline.setValue(0)
        self.timeline.setMaximum(0)
        self.position_changed(0)
        self.name.clear()
        self.distance.setValue(0)
        self.fixed_plane.setChecked(False)
        self.title.setText("Bir duvar. Daha iyi bir oyun.")
        for card, hint in zip(self.cards, (
            "İnceleme bekleyen adaylar", "Belirsizler ayrıca gösterilir",
            "Konumu belirlenen temaslar", "Tahmin · km/sa",
        )):
            card.value.setText("—")
            card.hint.setText(hint)
        for card in self.live_cards:
            card.value.setText("—")
        self.wall_chart.session = self.speed_chart.session = None
        self.wall_chart.target = [0.3, 0.3, 0.7, 0.7]
        self.wall_chart.update()
        self.speed_chart.update()
        self.shot_table.setRowCount(0)
        self.new_shot()
        self.device_preview.setText("Henüz analiz yok.")

    def load_history(self, item):
        try:
            session = self.store.load(item.data(Qt.UserRole))
            if not Path(session.video_path).is_file():
                raise ValueError("Kaynak video taşınmış. Orijinal dosyayı eski konumuna geri koy.")
            self.open_session(session)
        except Exception as exc:
            self.error(str(exc))

    def change_target(self, target):
        if self.session:
            self.session.calibration.target = target
            self.refresh_results()
            if len(self.session.calibration.wall) == 4:
                self.persist()

    def show_wall_shot(self, shot_id):
        if not self.session or not self.video_path:
            return
        for row, shot in enumerate(self.session.shots):
            if shot.id == shot_id and shot.wall_t is not None:
                self.shot_table.selectRow(row)
                self.player.pause()
                self.seek(round(shot.wall_t * 1000))
                self.canvas.t = shot.wall_t
                self.canvas.set_image(as_qimage(frame_at(self.video_path, shot.wall_t)))
                self.notify(
                    f"{row + 1}. vuruş · duvar adayı {shot.wall_t:.2f} sn · incelemek için Vuruş inceleme sekmesine geç."
                )
                return

    def show_speed_shot(self, shot_id):
        if not self.session:
            return
        for row, shot in enumerate(self.session.shots):
            if shot.id == shot_id:
                self.shot_table.selectRow(row)
                self.jump_to_shot(row)
                self.notify(
                    f"{row + 1}. vuruş açıldı. Eksik veya düşük güvenli hız için Vuruş inceleme bölümünde duvar zamanını kontrol et."
                )
                return

    def selected_shot(self):
        if self.session:
            return next((s for s in self.session.shots if s.id == self.edit_id), None)
        return None

    def select_shot(self):
        row = self.shot_table.currentRow()
        if not self.session or row < 0 or row >= len(self.session.shots):
            return
        shot = self.session.shots[row]
        self.edit_id = shot.id
        self.contact_time.setValue(shot.contact_t)
        self.wall_time.setValue(shot.wall_t or 0)
        self.kind.setCurrentIndex(["unknown", "forehand", "backhand"].index(shot.kind))
        self.edit_wall_xy = deepcopy(shot.wall_xy)
        self.point_label.setText("Duvar noktası: " + (str(shot.wall_xy) if shot.wall_xy else "belirlenmedi"))

    def jump_to_shot(self, row):
        if self.session and row < len(self.session.shots):
            self.player.pause()
            self.seek(round(self.session.shots[row].contact_t * 1000))
            self.tabs.setCurrentIndex(0)

    def new_shot(self):
        self.edit_id = None
        self.shot_table.clearSelection()
        self.contact_time.setValue(self.player.position() / 1000)
        self.wall_time.setValue(0)
        self.kind.setCurrentIndex(0)
        self.edit_wall_xy = None
        self.point_label.setText("Yeni vuruş · Raket zamanı mevcut video konumundan alındı.")

    def capture_wall_time(self):
        self.wall_time.setValue(self.player.position() / 1000)
        self.edit_wall_xy = None
        self.point_label.setText("Duvar zamanı alındı. Konumu yeniden seçebilirsin.")

    def pick_wall_point(self):
        if not self.session or len(self.session.calibration.wall) != 4:
            self.notify("Önce duvar kalibrasyonu yap.")
            return
        self.player.pause()
        self.seek(round(self.wall_time.value() * 1000))
        self.wall_capture = True
        self.canvas.mode = "view"
        self.tabs.setCurrentIndex(0)
        self.notify("Duvar temas anındaki top merkezine tıkla. Vuruş kaydedilene kadar bu seçim taslaktır.")

    def save_shot(self):
        if not self.session:
            return
        try:
            calibration = self.current_calibration()
            calibration.validate()
            t = self.contact_time.value()
            wall = self.wall_time.value() or None
            if t > self.session.duration or (wall is not None and not t < wall <= self.session.duration):
                raise ValueError("Duvar teması raketten sonra ve video süresi içinde olmalı.")
            if self.edit_wall_xy is not None and wall is None:
                raise ValueError("Konum kaydetmek için duvar zamanı gerekli.")
            shot = self.selected_shot()
            if shot is None:
                shot = Shot(contact_t=t, source="manual")
                self.session.shots.append(shot)
            shot.contact_t, shot.wall_t, shot.wall_xy = t, wall, deepcopy(self.edit_wall_xy)
            shot.kind = ["unknown", "forehand", "backhand"][self.kind.currentIndex()]
            shot.reviewed = True
            self.edit_id = shot.id
            self.session.calibration = calibration
            self.session.name = self.name.text().strip() or self.session.name
            self.session.shots.sort(key=lambda s: s.contact_t)
            self.persist()
            self.refresh_results()
            self.notify("Vuruş kaydedildi. İlk otomatik tespit ayrı olarak korunuyor.")
        except ValueError as exc:
            self.error(str(exc))

    def toggle_shot(self):
        shot = self.selected_shot()
        if shot:
            shot.included = not shot.included
            self.persist()
            self.refresh_results()

    def export_results(self):
        if not self.session or self.is_busy():
            return
        path, chosen = QFileDialog.getSaveFileName(
            self,
            "Sonuçları dışa aktar",
            "antrenman",
            "JSON (*.json);;CSV (*.csv);;İşaretlenmiş sessiz video (*.mp4)",
        )
        if not path:
            return
        suffix = ".mp4" if "mp4" in chosen else ".csv" if "csv" in chosen else ".json"
        if not path.lower().endswith(suffix):
            path += suffix
        try:
            if suffix == ".mp4":
                session = deepcopy(self.session)
                self.run_work(
                    lambda progress, stop: export_video(session, path, progress, stop),
                    lambda _: self.notify("İşaretlenmiş video kaydedildi (sessiz): " + path),
                )
            else:
                (export_csv if suffix == ".csv" else export_json)(self.session, path)
                self.notify("Kaydedildi: " + path)
        except Exception as exc:
            self.error(str(exc))

    def refresh_ports(self):
        from serial.tools.list_ports import comports

        self.ports.clear()
        for port in comports():
            self.ports.addItem(f"{port.device} · {port.description}", port.device)

    def send_device(self):
        if not self.session:
            self.notify("Önce bir antrenman yükle.")
            return
        port = self.ports.currentData()
        if not port:
            self.notify("ESP32 bağlı değil. USB kablosunu takıp portları yenile.")
            return
        session = deepcopy(self.session)
        self.run_work(
            lambda progress, stop: send_summary(session, port),
            lambda _: self.notify("ESP32 sonuçları aldığını doğruladı."),
        )

    def closeEvent(self, event):
        if self.is_busy():
            self.cancel_work()
            self.notify("İşlem durduruluyor. Bittikten sonra pencereyi kapatabilirsin.")
            event.ignore()
        else:
            self.player.stop()
            event.accept()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--screenshot", help="Save a UI screenshot and exit, for visual QA")
    parser.add_argument("--data-dir")
    args = parser.parse_args()
    if args.screenshot:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication(sys.argv[:1])
    # Windows' offscreen Qt plugin does not enumerate system fonts for QA images.
    if args.screenshot:
        for filename in ("segoeui.ttf", "segoeuib.ttf", "consola.ttf"):
            font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / filename
            if font_path.is_file():
                QFontDatabase.addApplicationFont(str(font_path))
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = MainWindow(args.data_dir)
    window.show()
    if args.demo:
        QTimer.singleShot(100, window.load_demo)
    if args.screenshot:

        def capture():
            window.grab().save(args.screenshot)
            app.quit()

        QTimer.singleShot(3500, capture)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
