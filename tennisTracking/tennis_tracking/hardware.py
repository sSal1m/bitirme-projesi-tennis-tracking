from __future__ import annotations

import json
import time

from .domain import Session


def display_packet(session: Session) -> bytes:
    return (
        json.dumps(
            {"v": 1, "session": session.id[:12], **session.summary()}, allow_nan=False, separators=(",", ":")
        )
        + "\n"
    ).encode("ascii")


def send_summary(session: Session, port: str) -> None:
    import serial

    with serial.Serial(port, 115200, timeout=0.5, write_timeout=2) as connection:
        # Opening USB serial resets common ESP32 development boards.
        time.sleep(2)
        connection.reset_input_buffer()
        connection.write(display_packet(session))
        connection.flush()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if connection.readline().strip() == b'{"v":1,"ack":true}':
                return
        raise RuntimeError("Ekran yanıt vermedi. Kart yazılımını ve COM portunu kontrol et.")
