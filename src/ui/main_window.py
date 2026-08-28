"""앱 컨트롤러: 고양이 위젯 ↔ 파이프라인 ↔ 다이얼로그 배선."""
from __future__ import annotations

import logging

from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

from src import config as cfg
from src.ui.cat_widget import CatWidget

log = logging.getLogger(__name__)


class AppController:
    def __init__(self):
        self.config = cfg.Config.load()
        self.cat = CatWidget(self.config)
        self.cat.items_received.connect(self.on_items)
        self.cat.unsupported.connect(self.on_unsupported)
        self.cat.settings_requested.connect(self.open_settings)
        self.cat.inbox_requested.connect(self.import_inbox)
        self.cat.quit_requested.connect(QApplication.instance().quit)

    # ---- 슬롯 (#10~#12, v0.3 에서 실제 구현으로 교체)
    def on_items(self, items: list) -> None:
        log.info("입력 %d건 수신: %s", len(items), [i.short for i in items])
        self.cat.set_queue_size(len(items))
        # 파이프라인 워커(#10) 연결 전까지는 수신 확인만
        self.cat.set_busy(True, "eating")
        from PySide6.QtCore import QTimer

        QTimer.singleShot(1500, lambda: (self.cat.set_queue_size(0), self.cat.set_busy(False)))

    def on_unsupported(self, msg: str) -> None:
        log.info("미지원 입력: %s", msg)
        self.cat.face.setToolTip(msg)

    def open_settings(self) -> None:
        QMessageBox.information(self.cat, "catmoa", "설정 화면은 #12 에서 구현됩니다.")

    def import_inbox(self) -> None:
        QMessageBox.information(self.cat, "catmoa", "인박스 가져오기는 #16 에서 구현됩니다.")

    def show(self) -> None:
        self.cat.show()


def create_main_widget() -> QWidget:
    ctrl = AppController()
    ctrl.cat._controller = ctrl  # 수명 유지
    return ctrl.cat
