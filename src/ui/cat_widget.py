"""고양이 플로팅 위젯.

- 프레임리스·투명·항상 위. 드래그로 이동, 위치 저장.
- 상태머신: idle / hover / drag / thinking / eating / happy / error / sleeping
- 입력 수신: 파일·텍스트·이미지 드롭, 호버 중 붙여넣기(⌘V/Ctrl+V), 우클릭 메뉴
- 큐 대기 수 배지, 호버 시 ⚙ 설정 아이콘
"""
from __future__ import annotations

import io
import logging
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice, QMimeData, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QGuiApplication, QImage, QKeySequence, QMouseEvent
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMenu, QVBoxLayout, QWidget

from src import config as cfg
from src.parsers import is_supported
from src.pipeline.items import InputItem
from src.ui.styles import CAT_FACES, FRAME_MS, STATE_TIPS, WIDGET_QSS

log = logging.getLogger(__name__)

BUSY_STATES = {"thinking", "eating"}
TRANSIENT_MS = {"happy": 2500, "error": 4000}
SLEEP_AFTER_MS = 5 * 60 * 1000


class CatWidget(QWidget):
    items_received = Signal(list)        # list[InputItem]
    unsupported = Signal(str)            # 사용자 안내 메시지
    settings_requested = Signal()
    inbox_requested = Signal()
    quit_requested = Signal()

    def __init__(self, config: cfg.Config, parent: QWidget | None = None):
        super().__init__(parent)
        self.config = config
        self._state = "idle"
        self._frame = 0
        self._drag_offset: QPoint | None = None
        self._queue_size = 0
        self._busy = False

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setStyleSheet(WIDGET_QSS)

        # ---- 레이아웃: [배지 ⚙] 위 줄, 얼굴 아래 줄
        top = QHBoxLayout()
        top.setContentsMargins(6, 0, 6, 0)
        self.badge = QLabel("", objectName="badge")
        self.badge.hide()
        self.gear = QLabel("⚙", objectName="gear")
        self.gear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.gear.setToolTip("설정")
        self.gear.hide()
        self.gear.mousePressEvent = lambda e: self.settings_requested.emit()  # type: ignore[assignment]
        top.addWidget(self.badge)
        top.addStretch(1)
        top.addWidget(self.gear)

        self.face = QLabel(objectName="catFace")
        self.face.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.face.setProperty("state", "idle")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addLayout(top)
        root.addWidget(self.face)

        # ---- 타이머
        self._anim = QTimer(self)
        self._anim.timeout.connect(self._tick)
        self._transient = QTimer(self)
        self._transient.setSingleShot(True)
        self._transient.timeout.connect(self._end_transient)
        self._sleep = QTimer(self)
        self._sleep.setSingleShot(True)
        self._sleep.timeout.connect(lambda: self._enter("sleeping"))

        self._enter("idle")
        self._restore_position()

    # ------------------------------------------------------------ 상태
    @property
    def state(self) -> str:
        return self._state

    def set_busy(self, busy: bool, phase: str = "eating") -> None:
        """파이프라인 워커가 호출. busy=True면 thinking/eating, False면 happy→idle."""
        self._busy = busy
        if busy:
            self._enter(phase)
        elif self._state in BUSY_STATES:
            self._enter("happy")

    def set_phase(self, phase: str) -> None:
        if self._busy and phase in BUSY_STATES:
            self._enter(phase)

    def show_error(self, message: str = "") -> None:
        self._busy = False
        self._enter("error")
        if message:
            self.face.setToolTip(message)

    def set_queue_size(self, n: int) -> None:
        self._queue_size = n
        if n > 0:
            self.badge.setText(f"{n}")
            self.badge.show()
        else:
            self.badge.hide()

    def _enter(self, state: str) -> None:
        if state == self._state and self._anim.isActive():
            return
        self._state = state
        self._frame = 0
        self.face.setProperty("state", state)
        self.face.style().unpolish(self.face)
        self.face.style().polish(self.face)
        self.face.setToolTip(STATE_TIPS.get(state, ""))
        self._paint()
        self._anim.start(FRAME_MS.get(state, 600))
        self._transient.stop()
        if state in TRANSIENT_MS:
            self._transient.start(TRANSIENT_MS[state])
        if state == "idle":
            self._sleep.start(SLEEP_AFTER_MS)
        else:
            self._sleep.stop()

    def _end_transient(self) -> None:
        if self._busy:
            self._enter("eating")
        elif self.underMouse():
            self._enter("hover")
        else:
            self._enter("idle")

    def _tick(self) -> None:
        frames = CAT_FACES.get(self._state, ["(=^･ω･^=)"])
        self._frame = (self._frame + 1) % len(frames)
        self._paint()

    def _paint(self) -> None:
        frames = CAT_FACES.get(self._state, ["(=^･ω･^=)"])
        self.face.setText(frames[self._frame % len(frames)])
        self.adjustSize()

    # ------------------------------------------------------------ 마우스 / 이동
    def enterEvent(self, event) -> None:
        self.gear.show()
        if not self._busy and self._state in ("idle", "sleeping"):
            self._enter("hover")
        # 호버 중 ⌘V 를 받기 위해 포커스 획득
        self.activateWindow()
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.gear.hide()
        if self._state == "hover":
            self._enter("idle")
        super().leaveEvent(event)

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            e.accept()
        else:
            super().mousePressEvent(e)

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        if self._drag_offset is not None and e.buttons() & Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_offset)
            e.accept()

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        if self._drag_offset is not None:
            self._drag_offset = None
            self._save_position()
        super().mouseReleaseEvent(e)

    def contextMenuEvent(self, e) -> None:
        menu = QMenu(self)
        a_paste = QAction("붙여넣기", self)
        a_paste.triggered.connect(self.paste_from_clipboard)
        a_inbox = QAction("Google Tasks 인박스 가져오기", self)
        a_inbox.triggered.connect(self.inbox_requested.emit)
        a_settings = QAction("설정…", self)
        a_settings.triggered.connect(self.settings_requested.emit)
        a_quit = QAction("종료", self)
        a_quit.triggered.connect(self.quit_requested.emit)
        menu.addAction(a_paste)
        menu.addAction(a_inbox)
        menu.addSeparator()
        menu.addAction(a_settings)
        menu.addSeparator()
        menu.addAction(a_quit)
        menu.exec(e.globalPos())

    def keyPressEvent(self, e) -> None:
        if e.matches(QKeySequence.StandardKey.Paste):
            self.paste_from_clipboard()
            e.accept()
            return
        super().keyPressEvent(e)

    # ------------------------------------------------------------ 위치 저장/복원
    def _restore_position(self) -> None:
        x, y = self.config.ui.widget_x, self.config.ui.widget_y
        screen = QGuiApplication.primaryScreen()
        geo = screen.availableGeometry() if screen else None
        self.adjustSize()
        if x < 0 or y < 0 or (geo and not geo.contains(QPoint(x, y))):
            if geo:
                x = geo.right() - self.width() - 24
                y = geo.bottom() - self.height() - 24
            else:
                x, y = 100, 100
        self.move(x, y)

    def _save_position(self) -> None:
        p = self.pos()
        self.config.ui.widget_x, self.config.ui.widget_y = p.x(), p.y()
        try:
            self.config.save()
        except OSError as e:
            log.warning("위치 저장 실패: %s", e)

    # ------------------------------------------------------------ 드롭 / 붙여넣기
    def dragEnterEvent(self, e) -> None:
        md = e.mimeData()
        if md.hasUrls() or md.hasImage() or md.hasText():
            e.acceptProposedAction()
            if not self._busy:
                self._enter("drag")

    def dragLeaveEvent(self, e) -> None:
        if self._state == "drag":
            self._enter("hover" if self.underMouse() else "idle")

    def dropEvent(self, e) -> None:
        items = self.items_from_mime(e.mimeData(), source="드롭")
        e.acceptProposedAction()
        self._deliver(items)

    def paste_from_clipboard(self) -> None:
        md = QApplication.clipboard().mimeData()
        items = self.items_from_mime(md, source="클립보드")
        self._deliver(items)

    def _deliver(self, items: list[InputItem]) -> None:
        if items:
            self.items_received.emit(items)
            if not self._busy:
                self._enter("thinking")
        else:
            self.unsupported.emit("일정으로 읽을 수 있는 내용이 없습니다 (파일: hwp/hwpx/pdf/이미지, 또는 텍스트·이미지).")
            self._enter("error")

    def items_from_mime(self, md: QMimeData, source: str = "") -> list[InputItem]:
        """QMimeData → InputItem 목록. 우선순위: 파일 URL > 이미지 > 텍스트."""
        items: list[InputItem] = []
        unsupported: list[str] = []
        if md.hasUrls():
            for url in md.urls():
                if not url.isLocalFile():
                    continue
                p = Path(url.toLocalFile())
                if p.is_dir():
                    for child in sorted(p.iterdir()):
                        if child.is_file() and is_supported(child):
                            items.append(InputItem("file", child))
                elif is_supported(p):
                    items.append(InputItem("file", p))
                else:
                    unsupported.append(p.name)
            if items or unsupported:
                if unsupported:
                    self.unsupported.emit("지원하지 않는 파일: " + ", ".join(unsupported[:5]))
                return items
        if md.hasImage():
            img = md.imageData()
            if isinstance(img, QImage) and not img.isNull():
                items.append(InputItem("image", qimage_to_png(img), source_label=f"{source} 이미지"))
                return items
        if md.hasText():
            text = md.text().strip()
            if text:
                # 텍스트가 실제 존재하는 파일 경로면 파일로 취급
                p = Path(text)
                if len(text) < 1024 and "\n" not in text and p.exists() and p.is_file() and is_supported(p):
                    items.append(InputItem("file", p))
                else:
                    items.append(InputItem("text", text, source_label=f"{source} 텍스트"))
        return items


def qimage_to_png(img: QImage) -> bytes:
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    data = bytes(buf.data())
    buf.close()
    return data
