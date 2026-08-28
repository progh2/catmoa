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
from PySide6.QtGui import QAction, QCursor, QFont, QFontMetrics, QGuiApplication, QImage, QKeySequence, QMouseEvent
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMenu, QVBoxLayout, QWidget

from src import config as cfg
from src.parsers import is_supported
from src.pipeline.items import InputItem
from src.ui.cat_faces import load_cat_images
from src.ui.styles import CAT_FACES, FRAME_MS, MONO_FAMILY, STATE_TIPS, WIDGET_QSS

FACE_FONT_PX = 20

log = logging.getLogger(__name__)

BUSY_STATES = {"thinking", "eating"}
TRANSIENT_MS = {"happy": 2500, "error": 4000, "annoyed": 3000, "empty": 3000, "searching": 1500}
HOVER_STATES = {"hover", "hover_tl", "hover_tr", "hover_bl", "hover_br"}
IDLE_STATES = {"idle", "bored", "sleeping"} | HOVER_STATES
BORED_AFTER_MS = 5 * 60 * 1000       # 입력 없이 5분 → 지루함
SLEEP_AFTER_MS = 30 * 60 * 1000      # 30분 → 잠


class HairpinBadge(QWidget):
    """고양이 머리에 꽂은 머리핀 모양의 업데이트 배지 — 기울어진 빨간 알약 + ⬆."""
    clicked = Signal()
    ANGLE = -18

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._s = 1.0
        self.set_scale(1.0)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def set_scale(self, scale: float) -> None:
        """고양이 배율에 맞춰 핀 크기도 조절 (0.7~2.2 배 범위로 완만하게)."""
        self._s = max(0.7, min(2.2, 0.55 + 0.45 * scale))
        self.setFixedSize(int(44 * self._s), int(30 * self._s))
        self.update()

    def paintEvent(self, e) -> None:
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QColor, QPainter, QPen

        s = self._s
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.translate(self.width() / 2, self.height() / 2)
        p.rotate(self.ANGLE)
        w, h = 34 * s, 16 * s
        rect = QRectF(-w / 2, -h / 2, w, h)
        p.setPen(QPen(QColor(150, 20, 30), 1.5 * s))
        p.setBrush(QColor(226, 48, 58))
        p.drawRoundedRect(rect, h / 2, h / 2)
        # 핀 광택
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 70))
        p.drawRoundedRect(QRectF(-w / 2 + 3 * s, -h / 2 + 2 * s, w - 6 * s, h / 2 - 2 * s), 4 * s, 4 * s)
        f = p.font()
        f.setPixelSize(max(8, int(12 * s)))
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("white"))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, "⬆ new")
        p.end()

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            e.accept()


class CatWidget(QWidget):
    items_received = Signal(list)        # list[InputItem]
    unsupported = Signal(str)            # 사용자 안내 메시지
    settings_requested = Signal()
    update_requested = Signal()          # ⬆ 배지 클릭 → 설정의 업데이트 탭
    inbox_requested = Signal()
    coolm_requested = Signal()           # 쿨메신저 지금 확인
    hide_requested = Signal()            # 트레이로 숨기기
    quit_requested = Signal()

    def __init__(self, config: cfg.Config, parent: QWidget | None = None):
        super().__init__(parent)
        self.config = config
        self._state = "idle"
        self._frame = 0
        self._drag_offset: QPoint | None = None
        self._queue_size = 0
        self._busy = False
        self._scale = max(0.5, min(3.0, float(getattr(config.ui, "cat_scale", 1.0) or 1.0)))

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)      # 버튼을 누르지 않아도 mouseMoveEvent (시선 추적)
        self.setStyleSheet(WIDGET_QSS)

        # ---- 레이아웃: [배지 ⚙] 위 줄, 얼굴 아래 줄
        top = QHBoxLayout()
        top.setContentsMargins(6, 0, 6, 0)
        self.badge = QLabel("", objectName="badge")
        self.badge.hide()
        # 업데이트 배지: 고양이 머리에 꽂은 머리핀처럼 (레이아웃 밖 오버레이, 기울어진 빨간 핀)
        self.update_badge = HairpinBadge(self)
        self.update_badge.set_scale(self._scale)
        self.update_badge.clicked.connect(self.update_requested.emit)
        self.update_badge.hide()
        # 숨겨져 있어도 자리를 차지하게 → 배지 표시 때 창 크기가 변하지 않는다
        sp = self.badge.sizePolicy()
        sp.setRetainSizeWhenHidden(True)
        self.badge.setSizePolicy(sp)
        self.badge.setText("00")          # 자리 확보용 최대 폭 텍스트로 크기 계산
        top.addWidget(self.badge)
        top.addStretch(1)

        self.face = QLabel(objectName="catFace")
        self.face.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.face.setProperty("state", "idle")
        # 이미지 고양이: assets/cat 또는 사용자 폴더에 PNG 가 있으면 이미지 모드, 없으면 텍스트 모드
        self._images = self._load_images()
        self.face.setProperty("mode", "image" if self._images else "text")
        self._fix_face_size()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addLayout(top)
        root.addWidget(self.face)
        # 위 줄(배지/⚙) 높이를 고정하고 창 전체를 고정 크기로 잠근다
        top_h = self.badge.sizeHint().height()
        self.badge.setFixedHeight(top_h)
        self.badge.setText("")
        # face 는 _fix_face_size 에서 setFixedSize 됨 → 레이아웃 전이라도 minimumWidth/Height 가 확정값
        self._top_h = top_h
        self._lock_size()

        # ---- 타이머
        self._anim = QTimer(self)
        self._anim.timeout.connect(self._tick)
        self._transient = QTimer(self)
        self._transient.setSingleShot(True)
        self._transient.timeout.connect(self._end_transient)
        self._bored = QTimer(self)
        self._bored.setSingleShot(True)
        self._bored.timeout.connect(lambda: self._enter("bored") if self._state == "idle" else None)
        self._sleep = QTimer(self)
        self._sleep.setSingleShot(True)
        self._sleep.timeout.connect(lambda: self._enter("sleeping") if self._state in ("idle", "bored") else None)

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

    def flash(self, state: str, message: str = "") -> None:
        """잠깐 보여주는 표정 (searching/empty/annoyed 등). 바쁜 중엔 무시."""
        if self._busy and state not in BUSY_STATES:
            return
        self._enter(state)
        if message:
            self.face.setToolTip(message)

    def set_update_available(self, version: str | None) -> None:
        """새 버전이 있으면 머리핀 배지를 항상 표시 (호버와 무관)."""
        if version:
            self.update_badge.setToolTip(f"새 버전 v{version} 이 있습니다 — 클릭해서 업데이트")
            self._place_update_badge()
            self.update_badge.show()
            self.update_badge.raise_()
        else:
            self.update_badge.hide()

    def _place_update_badge(self) -> None:
        """머리핀 위치: 이미지 모드는 오른쪽 귀 아래(머리 오른쪽 위), 텍스트 모드는 말풍선 오른쪽 위 모서리."""
        b = self.update_badge
        fw, fh = self.face.minimumWidth(), self.face.minimumHeight()
        top = getattr(self, "_top_h", 0)
        if self._images:
            x = int(fw * 0.66)
            y = top + int(fh * 0.16)
        else:
            x = fw - b.width() + 6
            y = max(0, top - b.height() // 2 + 2)
        b.move(x, y)

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
            self._bored.start(BORED_AFTER_MS)
            self._sleep.start(SLEEP_AFTER_MS)
        elif state not in ("bored",):
            self._bored.stop()
            self._sleep.stop()

    def _end_transient(self) -> None:
        if self._busy:
            self._enter("eating")
        elif self.underMouse():
            self._enter(self.hover_state_for(self.mapFromGlobal(QCursor.pos())))
        else:
            self._enter("idle")

    @property
    def image_mode(self) -> bool:
        return self._images is not None

    @property
    def scale(self) -> float:
        return self._scale

    def _load_images(self):
        screen = QGuiApplication.primaryScreen()
        return load_cat_images(dpr=screen.devicePixelRatio() if screen else 2.0, scale=self._scale)

    def _lock_size(self) -> None:
        """face 고정 크기(+배지 줄)로 창을 잠그고 머리핀 위치를 다시 잡는다."""
        fw, fh = self.face.minimumWidth(), self.face.minimumHeight()
        self.setFixedSize(fw, self._top_h + fh)
        self._place_update_badge()

    def set_scale(self, scale: float) -> None:
        """고양이 크기 배율 변경 (0.5~3.0). 이미지 재로딩 → 크기 재계산 → 현재 표정 다시 그림."""
        scale = max(0.5, min(3.0, float(scale or 1.0)))
        if abs(scale - self._scale) < 1e-6:
            return
        self._scale = scale
        self._images = self._load_images()
        self.update_badge.set_scale(scale)
        self.face.setProperty("mode", "image" if self._images else "text")
        self.face.setMinimumSize(0, 0)
        self.face.setMaximumSize(16777215, 16777215)
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        self._fix_face_size()
        self._lock_size()
        self._paint()

    def _frame_count(self) -> int:
        if self._images:
            return max(1, len(self._images.frames_for(self._state)))
        return len(CAT_FACES.get(self._state, ["(=^･ω･^=)"]))

    def _tick(self) -> None:
        self._frame = (self._frame + 1) % self._frame_count()
        self._paint()

    def _paint(self) -> None:
        if self._images:
            frames = self._images.frames_for(self._state)
            if frames:
                self.face.setPixmap(frames[self._frame % len(frames)])
            return
        frames = CAT_FACES.get(self._state, ["(=^･ω･^=)"])
        self.face.setText(frames[self._frame % len(frames)])

    def _fix_face_size(self) -> None:
        """모든 표정 프레임 중 가장 넓은/높은 것에 맞춰 크기를 고정 → 상태가 바뀌어도 창 크기 불변."""
        if self._images:
            w, h = self._images.logical_size
            self.face.setFixedSize(w, h)
            return
        # 폰트를 코드에서 지정해야 QSS 적용 전에도 정확히 측정된다 (QSS 폰트는 show 이후에나 반영됨)
        font = QFont()
        font.setFamilies([f.strip() for f in MONO_FAMILY.split(",")])
        font.setPixelSize(max(8, int(FACE_FONT_PX * self._scale)))
        self.face.setFont(font)
        fm = QFontMetrics(font)
        frames = [f for fs in CAT_FACES.values() for f in fs]
        w = max(fm.horizontalAdvance(f) for f in frames)
        h = fm.height()
        # QSS: padding 10px 16px + border 2px, 이모지 폭 여유
        self.face.setFixedSize(w + 16 * 2 + 2 * 2 + 12, h + 10 * 2 + 2 * 2)

    # ------------------------------------------------------------ 마우스 / 이동
    def hover_state_for(self, pos) -> str:
        """위젯 좌표 pos 가 어느 사분면인지 → hover_tl / hover_tr / hover_bl / hover_br (마우스를 쳐다보는 표정)."""
        cx, cy = self.width() / 2, self.height() / 2
        v = "t" if pos.y() < cy else "b"
        h = "l" if pos.x() < cx else "r"
        return f"hover_{v}{h}"

    def _hover_at(self, pos) -> None:
        st = self.hover_state_for(pos)
        if st != self._state:
            self._enter(st)

    def enterEvent(self, event) -> None:
        if not self._busy and self._state in IDLE_STATES:
            self._hover_at(event.position() if hasattr(event, "position") else self.mapFromGlobal(QCursor.pos()))
        # 호버 중 ⌘V 를 받기 위해 포커스 획득
        self.activateWindow()
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        if self._state in HOVER_STATES:
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
            return
        if not self._busy and self._state in HOVER_STATES:
            self._hover_at(e.position())     # 마우스 방향에 따라 시선 변경

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
        a_coolm = QAction("쿨메신저 지금 확인", self)
        a_coolm.triggered.connect(self.coolm_requested.emit)
        a_settings = QAction("설정…", self)
        a_settings.triggered.connect(self.settings_requested.emit)
        a_hide = QAction("숨기기 (트레이 아이콘 클릭으로 복귀)", self)
        a_hide.triggered.connect(self.hide_requested.emit)
        a_quit = QAction("종료", self)
        a_quit.triggered.connect(self.quit_requested.emit)
        menu.addAction(a_paste)
        menu.addAction(a_inbox)
        if getattr(self, "coolm_available", True):
            menu.addAction(a_coolm)
        menu.addSeparator()
        menu.addAction(a_settings)
        menu.addSeparator()
        menu.addAction(a_hide)
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
            self.flash("annoyed")

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
