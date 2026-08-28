"""앱 컨트롤러: 고양이 위젯 ↔ 파이프라인 워커 ↔ 검토/설정 다이얼로그 배선."""
from __future__ import annotations

import logging
from collections import deque

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

from src import config as cfg
from src import updater
from src.gsync.registrar import Registrar, RegistrationReport
from src.gsync.tasks import TasksClient
from src.llm import create_provider
from src.pipeline.worker import PipelineFailure, PipelineResult, PipelineWorker
from src.sources.coolm_watcher import CoolmWatcher
from src.sources.inbox import fetch_inbox_items
from src.ui.cat_widget import CatWidget
from src.ui.review_dialog import Decision, ReviewDialog
from src.ui.settings_dialog import SettingsDialog, _Task

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
        self.cat.update_requested.connect(lambda: self.open_settings(tab="update"))
        self.cat.inbox_requested.connect(self.import_inbox)
        self._update_info = None
        self.cat.quit_requested.connect(self.quit)

        # 부모를 위젯으로 두어 종료 시 C++/Python 소유권 충돌("shared QObject was deleted directly")을 막는다
        self.worker = PipelineWorker(lambda: create_provider(self.config.llm), parent=self.cat)
        self.worker.phase.connect(self._on_phase)
        self.worker.queue_size.connect(self.cat.set_queue_size)
        self.worker.result.connect(self.on_result)
        self.worker.failed.connect(self.on_failed)
        self.worker.idle.connect(lambda: self.cat.set_busy(False))

        self._pending: deque[PipelineResult] = deque()
        self._review: ReviewDialog | None = None
        self._tasks: list[_Task] = []
        self._boxes: list[QMessageBox] = []

        # 쿨메신저 폴링 (설정에서 켠 경우에만 동작)
        self.coolm = CoolmWatcher(self.config, parent=self.cat)
        self.coolm.new_items.connect(self.on_items)
        self.coolm.error.connect(self._on_coolm_error)
        self.coolm.status.connect(lambda s: log.info("쿨메신저: %s", s))
        self.coolm.apply_config()

        # 시작 후 잠시 뒤 업데이트 확인 (설정에서 끌 수 있음)
        if self.config.update.check_on_start:
            QTimer.singleShot(5000, self.check_update)

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

    # ------------------------------------------------------------ 등록
    def register(self, decisions: list[Decision], res: PipelineResult) -> None:
        if not decisions:
            return
        if not self.google.is_logged_in():
            QMessageBox.warning(self.cat, "catmoa", "Google에 로그인되어 있지 않습니다.\n설정 → Google 에서 로그인한 뒤 다시 등록하세요.")
            return
        origin = None
        if res.item.kind == "inbox_task" and res.item.origin_ref and ":" in res.item.origin_ref:
            origin = tuple(res.item.origin_ref.split(":", 1))
        registrar = Registrar(self.google, self.config.schedule)
        self.cat.set_busy(True, "eating")
        self.cat.face.setToolTip("Google에 등록 중…")
        self._run_bg(lambda: registrar.register(decisions, origin_task=origin),
                     self._on_registered, lambda m: self._on_registered(RegistrationReport(failures=[m])))

    def _on_registered(self, rep: RegistrationReport) -> None:
        if rep.ok:
            self.cat.set_busy(False)
            self.cat.face.setToolTip(f"등록 완료: {len(rep.successes)}건")
        else:
            self.cat.show_error(f"등록 실패 {len(rep.failures)}건")
            box = QMessageBox(QMessageBox.Icon.Warning, "등록 결과", rep.summary(), parent=None)
            box.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
            box.show()
            self._boxes.append(box)
        log.info("등록 결과: %s", rep.summary().replace("\n", " | "))

    def _run_bg(self, fn, on_done, on_error) -> None:
        t = _Task(fn)
        t.done.connect(on_done)
        t.error.connect(on_error)
        t.finished.connect(lambda: self._tasks.remove(t) if t in self._tasks else None)
        self._tasks.append(t)
        t.start()

    # ------------------------------------------------------------ 기타
    def open_settings(self, tab: str | None = None) -> None:
        dlg = SettingsDialog(self.config, google_auth=self.google, parent=None,
                             initial_tab=tab, update_info=self._update_info, quit_callback=self.quit)
        dlg.saved.connect(self._on_settings_saved)
        dlg.exec()

    # ------------------------------------------------------------ 업데이트
    def check_update(self) -> None:
        def done(info):
            self._update_info = info
            if info and info.version != self.config.update.skipped_version:
                self.cat.set_update_available(info.version)
                log.info("새 버전: v%s", info.version)
            else:
                self.cat.set_update_available(None)

        self._run_bg(updater.check_latest, done, lambda m: log.info("업데이트 확인 실패: %s", m))

    def _on_settings_saved(self, config: cfg.Config) -> None:
        self.config = config
        self.cat.config = config
        self.coolm.apply_config(config)
        log.info("설정 저장: llm=%s/%s coolm=%s/%ss", config.llm.provider, config.llm.model,
                 config.coolm.enabled, config.coolm.poll_seconds)

    def _on_coolm_error(self, msg: str) -> None:
        self.cat.show_error(f"쿨메신저: {msg}")
        log.warning("쿨메신저 오류: %s", msg)

    def import_inbox(self) -> None:
        if not self.google.is_logged_in():
            QMessageBox.warning(self.cat, "catmoa", "Google에 로그인되어 있지 않습니다.\n설정 → Google 에서 로그인하세요.")
            return
        name = self.config.schedule.inbox_list_name
        self.cat.set_busy(True, "thinking")
        self.cat.face.setToolTip(f"Google Tasks '{name}' 가져오는 중…")

        def fetch():
            return fetch_inbox_items(TasksClient(self.google.tasks_service()), name)

        def done(result):
            items, _ = result
            if not items:
                self.cat.set_busy(False)
                self.cat.face.setToolTip(f"'{name}' 목록에 미완료 항목이 없습니다.")
                return
            self.on_items(items)

        def err(msg):
            self.cat.show_error(msg)
            if "목록이 없습니다" in msg:
                ans = QMessageBox.question(
                    None, "인박스 가져오기",
                    f"Google Tasks에 '{name}' 목록이 없습니다.\n지금 만들까요? (휴대폰 Tasks 앱에서 이 목록에 메모를 적어두면 고양이가 가져옵니다)")
                if ans == QMessageBox.StandardButton.Yes:
                    self._run_bg(lambda: TasksClient(self.google.tasks_service()).create_tasklist(name),
                                 lambda r: self.cat.face.setToolTip(f"'{r[1]}' 목록을 만들었습니다. 메모를 적은 뒤 다시 가져오세요."),
                                 lambda m: self.cat.show_error(m))
                return
            box = QMessageBox(QMessageBox.Icon.Warning, "인박스 가져오기", msg, parent=None)
            box.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
            box.show()
            self._boxes.append(box)

        self._run_bg(fetch, done, err)

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
