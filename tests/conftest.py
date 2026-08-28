"""공통 픽스처: 세션 단위 QApplication (offscreen) + 종료 시 정리.

Linux offscreen 에서 QApplication 이 위젯/스레드보다 먼저 소멸하면 인터프리터 종료 시 segfault 가 난다.
여기서 모든 최상위 위젯을 닫고 이벤트를 비운 뒤 앱을 종료한다.
"""
import gc
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("CATMOA_NO_KEYRING", "1")

import pytest


@pytest.fixture(scope="session", autouse=True)
def _qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app
    for w in app.topLevelWidgets():
        try:
            w.close()
            w.deleteLater()
        except RuntimeError:
            pass
    app.processEvents()
    app.processEvents()
    gc.collect()
    app.quit()
    app.processEvents()
