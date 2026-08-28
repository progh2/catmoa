"""시스템 트레이 아이콘 — 항상 떠 있고, 고양이를 숨기거나 다시 부른다.

- 좌클릭(트리거): 숨김 ↔ 보이기 토글
- 우클릭 메뉴: 보이기/숨기기, 설정, 종료
- 고양이가 숨겨져 있으면 잠자는 고양이 아이콘(assets/icon_sleeping.png)
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon


def _assets_dir() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent.parent))
    return base / "assets"


def tray_icons() -> tuple[QIcon, QIcon]:
    """(보통 아이콘, 잠자는 아이콘). 잠자는 파일이 없으면 보통 아이콘으로 대체."""
    d = _assets_dir()
    normal = QIcon(str(d / "icon.png"))
    sleeping_path = d / "icon_sleeping.png"
    sleeping = QIcon(str(sleeping_path)) if sleeping_path.exists() else normal
    return normal, sleeping


class CatTray(QSystemTrayIcon):
    toggle_requested = Signal()      # 좌클릭 / 메뉴 '보이기·숨기기'
    settings_requested = Signal()
    quit_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._normal, self._sleeping = tray_icons()
        self._hidden = False
        self.setIcon(self._normal)
        self.setToolTip("catmoa — 클릭: 고양이 보이기/숨기기")

        self._menu = QMenu()
        self.act_toggle = QAction("고양이 숨기기", self._menu)
        self.act_toggle.triggered.connect(self.toggle_requested.emit)
        act_settings = QAction("설정…", self._menu)
        act_settings.triggered.connect(self.settings_requested.emit)
        act_quit = QAction("종료", self._menu)
        act_quit.triggered.connect(self.quit_requested.emit)
        self._menu.addAction(self.act_toggle)
        self._menu.addSeparator()
        self._menu.addAction(act_settings)
        self._menu.addSeparator()
        self._menu.addAction(act_quit)
        self.setContextMenu(self._menu)
        self.activated.connect(self._on_activated)

    def _on_activated(self, reason) -> None:
        # Trigger = 좌클릭 (macOS 는 메뉴가 뜨므로 메뉴의 토글 항목 사용), DoubleClick 도 토글
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.toggle_requested.emit()

    @property
    def hidden(self) -> bool:
        return self._hidden

    def set_hidden(self, hidden: bool) -> None:
        self._hidden = hidden
        self.setIcon(self._sleeping if hidden else self._normal)
        self.act_toggle.setText("고양이 보이기" if hidden else "고양이 숨기기")
        self.setToolTip("catmoa — 고양이가 자고 있어요. 클릭하면 다시 나타나요" if hidden
                        else "catmoa — 클릭: 고양이 숨기기")
