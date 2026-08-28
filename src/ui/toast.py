"""살짝 떴다 사라지는 안내 (고양이 위쪽). 포커스를 빼앗지 않는다."""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from src.ui.styles import FONT_FAMILY

TOAST_QSS = f"""
QLabel#toast {{
    font-family: {FONT_FAMILY};
    font-size: 13px;
    color: #3a2e1e;
    background: rgba(255, 250, 240, 245);
    border: 1px solid #f0c27b;
    border-radius: 10px;
    padding: 8px 12px;
}}
"""


class Toast(QWidget):
    """투명 최상위 창 안에 스타일된 QLabel 을 두고, 창 불투명도로 페이드아웃한다.
    (최상위 QLabel 에 직접 QSS 배경 + QGraphicsOpacityEffect 를 쓰면 배경이 그려지지 않는다)"""

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.label = QLabel(objectName="toast")
        self.label.setStyleSheet(TOAST_QSS)
        self.label.setWordWrap(True)
        self.label.setMaximumWidth(340)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.label)
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._fade.finished.connect(self._on_fade_done)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._fade_out)

    def show_message(self, text: str, *, near: QWidget | None = None, ms: int = 3200) -> None:
        self._fade.stop()
        self.label.setText(text)
        self.label.adjustSize()
        self.adjustSize()
        self._place(near)
        self.setWindowOpacity(1.0)
        self.show()
        self.raise_()
        self._hide_timer.start(ms)

    def text(self) -> str:
        return self.label.text()

    def _place(self, near: QWidget | None) -> None:
        screen = QGuiApplication.primaryScreen()
        geo = screen.availableGeometry() if screen else None
        w, h = self.sizeHint().width(), self.sizeHint().height()
        if near is not None and near.isVisible():
            g = near.frameGeometry()
            x = g.center().x() - w // 2
            y = g.top() - h - 8
            if geo is not None and y < geo.top():
                y = g.bottom() + 8
        elif geo is not None:
            x, y = geo.right() - w - 24, geo.bottom() - h - 120
        else:
            x, y = 100, 100
        if geo is not None:
            x = max(geo.left() + 4, min(x, geo.right() - w - 4))
        self.move(x, y)

    def _fade_out(self) -> None:
        self._fade.setDuration(500)
        self._fade.setStartValue(1.0)
        self._fade.setEndValue(0.0)
        self._fade.start()

    def _on_fade_done(self) -> None:
        if self.windowOpacity() < 0.05:
            self.hide()
