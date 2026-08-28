"""앱 컨트롤러: 고양이 위젯 ↔ 파이프라인 워커 ↔ 검토/설정 다이얼로그 배선."""
from __future__ import annotations

import logging
from collections import deque

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

from src import config as cfg
from src import updater
from src.gsync.calendar import CalendarClient
from src.gsync.dedupe import find_duplicates
from src.gsync.registrar import Registrar, RegistrationReport
from src.gsync.tasks import TasksClient
from src.ui.dedupe_dialog import DedupeDialog
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
        self.cat.coolm_requested.connect(self.coolm_check_now)
        self._update_info = None
        self.cat.quit_requested.connect(self.quit)

        self.tasklists: list[tuple[str, str]] = []   # Google Tasks 목록 (id, 이름) — 카테고리로 사용
        # 부모를 위젯으로 두어 종료 시 C++/Python 소유권 충돌("shared QObject was deleted directly")을 막는다
        self.worker = PipelineWorker(lambda: create_provider(self.config.llm), parent=self.cat,
                                     options_factory=self._extract_options)
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
        self.coolm.polling.connect(lambda: self.cat.flash("searching"))
        self.coolm.apply_config()

        # 시작 후 잠시 뒤 업데이트 확인 (설정에서 끌 수 있음)
        if self.config.update.check_on_start:
            QTimer.singleShot(5000, self.check_update)
        QTimer.singleShot(1500, self.refresh_tasklists)

    # ------------------------------------------------------------ 분류 옵션 / 태스크 목록
    def _extract_options(self) -> dict:
        s = self.config.schedule
        return {"kind_rules": s.kind_rules, "category_rules": s.category_rules,
                "categories": [name for _, name in self.tasklists]}

    def refresh_tasklists(self) -> None:
        if not self.google.is_logged_in():
            return

        def done(lists):
            self.tasklists = list(lists)
            log.info("Google Tasks 목록 %d개: %s", len(lists), [n for _, n in lists])

        self._run_bg(self.google.list_tasklists, done, lambda m: log.info("태스크 목록 조회 실패: %s", m))

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
            self.cat.flash("empty", f"{res.item.short}: 일정을 찾지 못했습니다.")
            self._show_next_review()
            return
        dlg = ReviewDialog(ex.items, self.config.schedule, source_label=res.item.short,
                           warnings=ex.warnings, preview_text=_preview_of(res), tasklists=self.tasklists)
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
        registrar = Registrar(self.google, self.config.schedule,
                              tasklists={name: tid for tid, name in self.tasklists})
        self.cat.set_busy(True, "thinking")
        self.cat.face.setToolTip("기존 일정과 중복 확인 중…")

        def check():
            cal = CalendarClient(self.google.calendar_service()) if any("calendar" in d.targets for d in decisions) else None
            tk = TasksClient(self.google.tasks_service()) if any("task" in d.targets for d in decisions) else None
            return find_duplicates(decisions, self.config.schedule, calendar=cal, tasks=tk,
                                   resolve_tasklist=lambda d: registrar._tasklist_for(d)[0])

        def after_check(result):
            for e in result.errors:
                log.warning("중복 검사: %s", e)
            if result.any:
                dlg = DedupeDialog(result.matches)
                if dlg.exec() != DedupeDialog.DialogCode.Accepted:
                    self.cat.set_busy(False)
                    self.cat.face.setToolTip("등록을 취소했습니다.")
                    return
                for m, choice in zip(result.matches, dlg.choices()):
                    m.decision.dedupe[m.target] = (choice, m.existing, m.tasklist_id)
            self._do_register(registrar, decisions, origin)

        self._run_bg(check, after_check, lambda m: (log.warning("중복 검사 실패, 그대로 등록: %s", m),
                                                    self._do_register(registrar, decisions, origin)))

    def _do_register(self, registrar: Registrar, decisions: list[Decision], origin) -> None:
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
                             initial_tab=tab, update_info=self._update_info, quit_callback=self.quit,
                             tasklists=self.tasklists, coolm_watcher=self.coolm)
        dlg.saved.connect(self._on_settings_saved)
        dlg.exec()
        if not getattr(self, "_quitting", False):
            self.refresh_tasklists()   # 로그인/목록 변경 반영

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

    def coolm_check_now(self) -> None:
        """우클릭 메뉴 → 쿨메신저 새 쪽지 강제 확인."""
        self.cat.flash("searching", "쿨메신저 새 쪽지 확인 중…")

        def done(msgs):
            n = self.coolm.deliver(msgs)
            if not n:
                self.cat.flash("empty", "쿨메신저: 새 쪽지가 없습니다.")

        self._run_bg(self.coolm.fetch_now, done, lambda m: self.cat.show_error(f"쿨메신저: {m}"))

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
        """종료. 업데이트 교체 스크립트가 PID 종료를 기다리므로, 스레드를 정리하고도 안 죽으면 강제 종료한다."""
        self._quitting = True
        try:
            self.coolm.apply_config(cfg.Config(coolm=cfg.CoolmSettings(enabled=False)))
        except Exception:  # noqa: BLE001
            pass
        self.worker.stop(1500)
        for t in list(self._tasks):
            t.wait(1500)
        for d in (self._review,):
            if d is not None:
                d.close()
        QApplication.instance().quit()
        # Qt 루프가 어떤 이유로든 안 끝나면(스레드 잔존 등) 3초 뒤 프로세스를 확실히 끝낸다
        import os
        import threading

        threading.Timer(3.0, lambda: os._exit(0)).start()

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
