"""Render the ESP32 summary screens on a PC.

`firmware/src/main.cpp` draws two pages on a 128x64 SSD1306 display. This
script reproduces that drawing on the computer so the hardware section can
be demonstrated and reviewed before the board is connected, and so the
screen layout can be checked without a physical OLED.

Usage:
    python scripts/oled_simulator.py data/<SESSION_ID>/session.json
    python scripts/oled_simulator.py data/<SESSION_ID>/session.json --out data/oled
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tennis_tracking.domain import Session  # noqa: E402

WIDTH, HEIGHT = 128, 64
SCALE = 6


def load_font() -> ImageFont.FreeTypeFont:
    """A small fixed-width font that fits the Adafruit 6x8 character cell."""
    candidates = (
        Path("C:/Windows/Fonts/consola.ttf"),
        Path("C:/Windows/Fonts/lucon.ttf"),
    )
    for path in candidates:
        if path.is_file():
            return ImageFont.truetype(str(path), 9)
    return ImageFont.load_default(size=9)


class Screen:
    """Minimal Adafruit GFX style canvas: 6x8 character cells, white pixels."""

    def __init__(self):
        self.image = Image.new("1", (WIDTH, HEIGHT), 0)
        self.draw = ImageDraw.Draw(self.image)
        self.font = load_font()
        self.x = 0
        self.y = 0

    def text(self, value: str) -> None:
        # The Adafruit 6x8 cell is fixed width, so every glyph is placed on
        # its own cell instead of using the font's natural advance.
        for index, char in enumerate(value):
            self.draw.text((self.x + index * 6, self.y - 1), char, fill=1, font=self.font)
        self.x += 6 * len(value)

    def println(self, value: str = "") -> None:
        self.text(value)
        self.x = 0
        self.y += 8

    def line(self, x0: int, y0: int, x1: int, y1: int) -> None:
        self.draw.line((x0, y0, x1, y1), fill=1, width=1)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.image.convert("L").resize((WIDTH * SCALE, HEIGHT * SCALE), Image.NEAREST).save(path)


def build_header(screen: Screen) -> None:
    screen.text("DUVAR TENIS")
    screen.line(0, 10, 127, 10)
    screen.x = 0
    screen.y = 16


def draw_summary(screen: Screen, summary: dict, page: int) -> None:
    """Mirror of render() in firmware/src/main.cpp for the summary state."""
    build_header(screen)
    if page == 0:
        screen.println(f"Vurus: {summary['strokes']}")
        screen.println(f"FH {summary['forehand']} / BH {summary['backhand']}")
        screen.println(f"Belirsiz: {summary['unknown']}")
        screen.println(f"Incelendi: {summary['reviewed']}/{summary['strokes']}")
    else:
        hit = summary.get("hit_rate")
        screen.println("Hedef: " + (f"{hit:.1f}%" if hit is not None else "--"))
        screen.println(f"Konumlu: {summary['localized']}")
        speed = summary.get("approach_kmh")
        screen.println("Tahmin: " + (f"{speed:.1f} km/h" if speed is not None else "--"))
        screen.println("Radar hizi degildir")


def draw_waiting(screen: Screen) -> None:
    build_header(screen)
    screen.println("USB baglantisi hazir")
    screen.println("Sonuc bekleniyor...")


def main() -> int:
    parser = argparse.ArgumentParser(description="ESP32 OLED ekranini PC'de ciz.")
    parser.add_argument("session", help="session.json dosyasi")
    parser.add_argument("--out", default="data/oled")
    args = parser.parse_args()

    path = Path(args.session).resolve()
    if not path.is_file():
        print(f"Session dosyasi bulunamadi: {path}")
        return 1

    session = Session.from_dict(json.loads(path.read_text("utf-8")))
    summary = session.summary()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    waiting = Screen()
    draw_waiting(waiting)
    waiting.save(out_dir / "oled_bekleme.png")

    for page in (0, 1):
        screen = Screen()
        draw_summary(screen, summary, page)
        name = "oled_sayfa1_ozet.png" if page == 0 else "oled_sayfa2_hedef_hiz.png"
        screen.save(out_dir / name)

    print(f"OLED ekranlari cizildi -> {out_dir}")
    print(f"  vurus={summary['strokes']} fh={summary['forehand']} bh={summary['backhand']} "
          f"belirsiz={summary['unknown']} incelendi={summary['reviewed']}")
    print(f"  hedef={summary.get('hit_rate')} konumlu={summary['localized']} "
          f"hiz={summary.get('approach_kmh')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
