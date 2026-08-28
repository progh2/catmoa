"""앱 컨트롤러: 고양이 위젯 ↔ 파이프라인 워커 ↔ 검토/설정 다이얼로그 배선."""
from __future__ import annotations

import logging
from collections import deque

from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

from src import config as cfg
from src.llm import create_provider
from src.pipeline.worker import PipelineFailure, PipelineResult, PipelineWorker
from src.ui.cat_widget import CatWidget
from src.ui.review_dialog import Decision, ReviewDialog
from src.ui.settings_dialog import SettingsDialog

log = logging.getLogger(__name__)


class AppController:
    def __init__(self):
        self.config = cfg.Config.load()
        from src.gsync.auth import GoogleAuth

        self.google = GoogleAuth()
        self.registrar = None         # v0.3 #14/#15: gsync.registrar.Registrar

        self.cat = CatWidget(self.config)
        self.cat.items_received.connect(self.on_items)
        self.cat.unsupported.connect(self.on_unsupported)
        self.cat.settings_requested.connect(self.open_settings)
        self.cat.inbox_requested.connect(self.import_inbox)
        self.cat.quit_requested.connect(self.quit)

        self.worker = PipelineWorker(lambda: create_provider(self.config.llm))
        self.worker.phase.connect(self._on_phase)
        self.worker.queue_size.connect(self.cat.set_queue_size)
        self.worker.result.connect(self.on_result)
        self.worker.failed.connect(self.on_failed)
        self.worker.idle.connect(lambda: self.cat.set_busy(False))

        self._pending: deque[PipelineResult] = deque()
        self._review: ReviewDialog | None = None

    # ------------------------------------------------------------ 입력 → 큐
    def on_items(self, items: list) -> None:
        log.info("입력 %d건: %s", len(items), [i.short for i in items])
        self.cat.set_busy(True, "thinking")
        self.worker.enqueue(items)

    def on_unsupported(self, msg: str) -> None:
        self.cat.face.setToolTip(msg)

    def _on_phase(self, phase: str) -> None:
        self.cat.set_busy(True, phase)

    # ------------------------------------------------------------ 결과 → 검토
    def on_result(self, res: PipelineResult) -> None:
        self._pending.append(res)
        self._show_next_review()

    def on_failed(self, f: PipelineFailure) -> None:
        self.cat.show_error(f"{f.item.short}: {f.message}")
        log.warning("실패: %s: %s", f.item.short, f.message)

    def _show_next_review(self) -> None:
        if self._review is not None or not self._pending:
            return
        res = self._pending.popleft()
        ex = res.extraction
        if not ex.items and not ex.warnings:
            self.cat.face.setToolTip(f"{res.item.short}: 일정을 찾지 못했습니다.")
            self._show_next_review()
            return
        dlg = ReviewDialog(ex.items, self.config.schedule, source_label=res.item.short,
                           warnings=ex.warnings, preview_text=_preview_of(res))
        dlg.submitted.connect(lambda ds, r=res: self.register(ds, r))
        dlg.finished.connect(self._on_review_closed)
        self._review = dlg
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _on_review_closed(self, *_) -> None:
        self._review = None
        self._show_next_review()

    # ------------------------------------------------------------ 등록 (v0.3에서 Registrar 연결)
    def register(self, decisions: list[Decision], res: PipelineResult) -> None:
        if not decisions:
            return
        if self.registrar is None:
            lines = [f"{'📅' if d.target == 'calendar' else '✅'} {d.item.describe_when()}  {d.item.title}"
                     + (f"  ⏰{d.alarm_minutes}분 전" if d.alarm_minutes is not None else "")
                     for d in decisions]
            QMessageBox.information(self.cat, "등록 (미리보기)",
                                    "Google 연동은 v0.3에서 연결됩니다. 선택한 항목:\n\n" + "\n".join(lines))
            return
        self.registrar.register(decisions, res)

    # ------------------------------------------------------------ 기타
    def open_settings(self) -> None:
        dlg = SettingsDialog(self.config, google_auth=self.google, parent=None)
        dlg.saved.connect(self._on_settings_saved)
        dlg.exec()

    def _on_settings_saved(self, config: cfg.Config) -> None:
        self.config = config
        log.info("설정 저장: llm=%s/%s", config.llm.provider, config.llm.model)

    def import_inbox(self) -> None:
        QMessageBox.information(self.cat, "catmoa", "인박스 가져오기는 v0.3(#16)에서 연결됩니다.")

    def quit(self) -> None:
        self.worker.stop(1000)
        QApplication.instance().quit()

    def show(self) -> None:
        self.cat.show()


def _preview_of(res: PipelineResult) -> str:
    it = res.item
    if it.kind in ("text", "coolm", "inbox_task"):
        return str(it.payload)
    if it.kind == "file":
        return f"(파일) {it.payload}"
    return ""


def create_main_widget() -> QWidget:
    ctrl = AppController()
    ctrl.cat._controller = ctrl  # 수명 유지
    return ctrl.cat
