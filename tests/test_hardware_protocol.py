"""Contract test for the PC <-> ESP32 summary protocol.

`firmware/src/main.cpp` validates every incoming line before it accepts the
numbers. This module reproduces that validation in Python so the packet
format is verified on the computer, without the board being connected.

If a field of `Session.summary()` is renamed, this test fails here instead
of on the display.
"""

from __future__ import annotations

import json

import pytest

from tennis_tracking.domain import Session
from tennis_tracking.hardware import display_packet

MAX_LINE_BYTES = 767
REQUIRED_COUNTERS = ("strokes", "forehand", "backhand", "unknown", "reviewed", "localized")
REQUIRED_NUMBERS = ("hit_rate", "approach_kmh")


def firmware_accepts(line: str) -> bool:
    """Port of receiveLine() in firmware/src/main.cpp."""
    try:
        obj = json.loads(line)
    except ValueError:
        return False
    if not isinstance(obj, dict):
        return False
    if obj.get("v") != 1:
        return False
    for field in REQUIRED_COUNTERS:
        value = obj.get(field)
        if not isinstance(value, int) or isinstance(value, bool):
            return False
    for field in REQUIRED_NUMBERS:
        value = obj.get(field)
        if value is not None and not isinstance(value, (int, float)):
            return False

    total = obj["strokes"]
    forehand = obj["forehand"]
    backhand = obj["backhand"]
    unknown = obj["unknown"]
    reviewed = obj["reviewed"]
    localized = obj["localized"]
    hit_rate = obj["hit_rate"]
    speed = obj["approach_kmh"]

    if min(total, forehand, backhand, unknown, reviewed, localized) < 0:
        return False
    if forehand + backhand + unknown != total:
        return False
    if reviewed > total or localized > total:
        return False
    if hit_rate is not None and not 0 <= hit_rate <= 100:
        return False
    if speed is not None and speed < 0:
        return False
    return True


def test_summary_packet_is_accepted_by_firmware_logic(demo):
    packet = display_packet(demo)
    assert packet.endswith(b"\n")
    assert len(packet) <= MAX_LINE_BYTES
    assert firmware_accepts(packet.decode("ascii"))


def test_packet_is_single_ascii_line(demo):
    packet = display_packet(demo)
    assert packet.count(b"\n") == 1
    packet.decode("ascii")


def test_firmware_rejects_inconsistent_counters(demo):
    payload = json.loads(display_packet(demo))
    broken = dict(payload)
    broken["forehand"] = broken["strokes"] + 1
    assert not firmware_accepts(json.dumps(broken))


def test_firmware_rejects_wrong_version(demo):
    payload = json.loads(display_packet(demo))
    broken = dict(payload)
    broken["v"] = 2
    assert not firmware_accepts(json.dumps(broken))


def test_firmware_rejects_out_of_range_hit_rate(demo):
    payload = json.loads(display_packet(demo))
    broken = dict(payload)
    broken["hit_rate"] = 140.0
    assert not firmware_accepts(json.dumps(broken))


def test_firmware_rejects_negative_speed(demo):
    payload = json.loads(display_packet(demo))
    broken = dict(payload)
    broken["approach_kmh"] = -1.0
    assert not firmware_accepts(json.dumps(broken))


def test_firmware_rejects_missing_counter(demo):
    payload = json.loads(display_packet(demo))
    broken = dict(payload)
    del broken["localized"]
    assert not firmware_accepts(json.dumps(broken))


def test_firmware_rejects_broken_line():
    assert not firmware_accepts("{not json")


@pytest.mark.parametrize("session_id", ["a" * 12, "0123456789ab"])
def test_session_prefix_is_twelve_characters(session_id, calibration):
    session = Session(video_path="v.mp4", calibration=calibration, id=session_id)
    payload = json.loads(display_packet(session))
    assert payload["session"] == session_id[:12]
