from fractions import Fraction

import av
import numpy as np

from tennis_tracking.video import audio_onsets


def test_stereo_audio_does_not_double_timestamps(tmp_path):
    path = tmp_path / "stereo.mkv"
    with av.open(str(path), "w") as output:
        video = output.add_stream("libx264", rate=10)
        video.width = video.height = 64
        video.pix_fmt = "yuv420p"
        audio = output.add_stream("pcm_s16le", rate=16000)
        audio.layout = "stereo"
        for index in range(10):
            vf = av.VideoFrame.from_ndarray(np.zeros((64, 64, 3), np.uint8), format="bgr24")
            vf.pts, vf.time_base = index, Fraction(1, 10)
            for packet in video.encode(vf):
                output.mux(packet)
            # Packed stereo: two adjacent values per audio sample.
            samples = np.zeros((1, 3200), dtype=np.int16)
            if index in (3, 7):
                samples[0, 0:80] = 30000
            af = av.AudioFrame.from_ndarray(samples, format="s16", layout="stereo")
            af.sample_rate = 16000
            af.pts, af.time_base = index * 1600, Fraction(1, 16000)
            for packet in audio.encode(af):
                output.mux(packet)
        for stream in (video, audio):
            for packet in stream.encode():
                output.mux(packet)
    peaks = audio_onsets(str(path))
    assert any(abs(t - 0.3) < 0.02 for t in peaks)
    assert any(abs(t - 0.7) < 0.02 for t in peaks)
    assert all(0 <= t < 1 for t in peaks)
