import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from tennis_tracking.domain import Calibration


@pytest.fixture
def calibration():
    return Calibration(wall=[[0.1, 0.1], [0.6, 0.1], [0.6, 0.7], [0.1, 0.7]])


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(scope="session")
def demo(tmp_path_factory):
    from tennis_tracking.demo import create_demo

    return create_demo(tmp_path_factory.mktemp("demo"))
