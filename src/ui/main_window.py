"""메인 위젯 팩토리.

#8 고양이 플로팅 위젯이 구현되면 이 팩토리가 그것을 반환한다.
그 전까지는 플레이스홀더를 띄워 실행 골격을 검증한다.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QWidget

from src.ui.styles import CAT_FACES, WIDGET_QSS


def create_main_widget() -> QWidget:
    w = QLabel(CAT_FACES["idle"])
    w.setObjectName("catFace")
    w.setStyleSheet(WIDGET_QSS)
    w.setAlignment(Qt.AlignmentFlag.AlignCenter)
    w.setWindowTitle("catmoa")
    w.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
    w.setToolTip("catmoa — 여기에 파일을 떨어뜨리세요 (준비 중)")
    return w
