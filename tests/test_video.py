from fractions import Fraction

import av
import numpy as np
import pytest

from tennis_tracking.analysis import AnalysisCancelled
from tennis_tracking.rendering import export_video
from tennis_tracking.video import audio_onsets, frame_at, frames, oriented, probe


def test_probe_and_seek(demo):
    info = probe(demo.video_path)
    assert (info.width, info.height, info.fps) == (960, 540, 30)
    assert info.duration == pytest.approx(10)
    assert frame_at(demo.video_path, 4).shape == (540, 960, 3)
    assert audio_onsets(demo.video_path) == []


def test_variable_frame_timestamps_are_not_frame_index_over_fps(tmp_path):
    path = tmp_path / "vfr.mp4"
    with av.open(str(path), "w") as output:
        stream = output.add_stream("libx264", rate=30)
        stream.width = stream.height = 64
        stream.pix_fmt = "yuv420p"
        stream.time_base = stream.codec_context.time_base = Fraction(1, 90000)
        for t in [0, 0.04, 0.11, 0.2]:
            frame = av.VideoFrame.from_ndarray(np.zeros((64, 64, 3), dtype=np.uint8), format="bgr24")
            frame.pts, frame.time_base = round(t * 90000), Fraction(1, 90000)
            for packet in stream.encode(frame):
                output.mux(packet)
        for packet in stream.encode():
            output.mux(packet)
    timestamps = [t for _, t, _ in frames(str(path))]
    assert timestamps == pytest.approx([0, 0.04, 0.11, 0.2], abs=0.0001)


def test_rotation_applied_before_calibration():
    class Rotated:
        rotation = 90

        def to_ndarray(self, format):
            return np.zeros((60, 100, 3), dtype=np.uint8)

    assert oriented(Rotated()).shape == (100, 60, 3)


def test_export_is_playable_and_preserves_timestamps(tmp_path, demo):
    output = tmp_path / "annotated.mp4"
    export_video(demo, str(output))
    info = probe(str(output))
    assert info.duration == pytest.approx(10, abs=0.05)
    assert len(list(frames(str(output)))) == 300
    assert not (tmp_path / "annotated.partial.mp4").exists()


def test_cancelled_export_leaves_no_partial_file(tmp_path, demo):
    output = tmp_path / "cancelled.mp4"
    with pytest.raises(AnalysisCancelled):
        export_video(demo, str(output), cancelled=lambda: True)
    assert not output.exists()
    assert not (tmp_path / "cancelled.partial.mp4").exists()


def test_export_cannot_overwrite_input(demo):
    with pytest.raises(ValueError):
        export_video(demo, demo.video_path)
