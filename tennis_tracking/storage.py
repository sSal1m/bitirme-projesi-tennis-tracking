from __future__ import annotations

import csv
import json
import shutil
import sqlite3
from pathlib import Path

from .domain import Session, approach_speed


class SessionStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = self.root / "sessions.sqlite3"
        with sqlite3.connect(self.db) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, created_at TEXT, "
                "name TEXT, video_path TEXT, summary TEXT)"
            )

    def save(self, session: Session) -> Path:
        folder = self.root / session.id
        folder.mkdir(exist_ok=True)
        dst = folder / "session.json"
        tmp = folder / "session.tmp"
        tmp.write_text(json.dumps(session.to_dict(), ensure_ascii=False, allow_nan=False), encoding="utf-8")
        tmp.replace(dst)
        with sqlite3.connect(self.db) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sessions VALUES (?, ?, ?, ?, ?)",
                (
                    session.id,
                    session.created_at,
                    session.name,
                    session.video_path,
                    json.dumps(session.summary()),
                ),
            )
        return dst

    def load(self, session_id: str) -> Session:
        if not session_id.isalnum():
            raise ValueError("Oturum kimliği geçersiz.")
        return Session.from_dict(json.loads((self.root / session_id / "session.json").read_text("utf-8")))

    def list(self) -> list[dict]:
        with sqlite3.connect(self.db) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute("SELECT * FROM sessions ORDER BY created_at DESC")]

    def delete(self, session_id: str) -> None:
        if not session_id or not session_id.isalnum():
            raise ValueError("Oturum kimliği geçersiz.")
        folder = self.root / session_id
        if folder.is_symlink() or folder.resolve() != self.root.resolve() / session_id:
            raise ValueError("Oturum klasörü veri dizininin dışında.")
        with sqlite3.connect(self.db) as conn:
            if not conn.execute("SELECT 1 FROM sessions WHERE id = ?", (session_id,)).fetchone():
                return
            if folder.exists():
                shutil.rmtree(folder)
            conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))


def export_json(session: Session, path: str | Path) -> None:
    Path(path).write_text(
        json.dumps(session.to_dict(), ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )


def export_csv(session: Session, path: str | Path) -> None:
    columns = [
        "id",
        "contact_s",
        "wall_s",
        "type",
        "wall_x",
        "wall_y",
        "approach_kmh_estimate",
        "confidence",
        "source",
        "reviewed",
        "included",
    ]
    with Path(path).open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        for s in session.shots:
            writer.writerow(
                [
                    s.id,
                    s.contact_t,
                    s.wall_t,
                    s.kind,
                    *(s.wall_xy or [None, None]),
                    approach_speed(s, session.calibration),
                    s.confidence,
                    s.source,
                    s.reviewed,
                    s.included,
                ]
            )
