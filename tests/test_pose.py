from pathlib import Path

import numpy as np
import pytest

from tennis_tracking.detection import PoseDetector


def test_real_pose_model_loads_and_handles_empty_frame():
    pytest.importorskip("mediapipe")
    model_path = Path(__file__).parents[1] / "models/pose_landmarker_lite.task"
    if not model_path.exists():
        pytest.skip("Official model not downloaded; run scripts/download_pose.py")
    detector = PoseDetector(str(model_path))
    try:
        blank = np.zeros((240, 320, 3), dtype=np.uint8)
        assert detector.detect(blank, 0) is None
        assert detector.detect(blank, 0.016) is None
    finally:
        detector.close()
