"""Open a saved session in the UI and capture a screenshot.

Used for presentation QA: it shows the same interface the user sees, but
with a real analysis session instead of the synthetic demo.

Usage:
    python scripts/screenshot_session.py data/<SESSION_ID>/session.json data/out.png
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tennis_tracking.app import STYLE, MainWindow  # noqa: E402
from tennis_tracking.domain import Session  # noqa: E402


def main() -> int:
    if len(sys.argv) < 3:
        print("Kullanim: python scripts/screenshot_session.py <session.json> <out.png>")
        return 1

    session_path = Path(sys.argv[1]).resolve()
    out_path = Path(sys.argv[2]).resolve()
    if not session_path.is_file():
        print(f"Session dosyasi bulunamadi: {session_path}")
        return 1

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication(sys.argv[:1])
    for filename in ("segoeui.ttf", "segoeuib.ttf", "consola.ttf"):
        font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / filename
        if font_path.is_file():
            QFontDatabase.addApplicationFont(str(font_path))
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)

    window = MainWindow()
    window.show()
    session = Session.from_dict(json.loads(session_path.read_text("utf-8")))

    def open_and_capture():
        window.open_session(session)
        window.tabs.setCurrentIndex(0)

        def capture():
            window.grab().save(str(out_path))
            print(f"Ekran goruntusu kaydedildi: {out_path}")
            app.quit()

        QTimer.singleShot(2500, capture)

    QTimer.singleShot(400, open_and_capture)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
