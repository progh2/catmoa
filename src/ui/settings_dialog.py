"""설정 다이얼로그: LLM / 일반 / Google / 쿨메신저 탭."""
from __future__ import annotations

import os
import platform
from pathlib import Path
from typing import Callable, Protocol

from PySide6.QtCore import QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QProgressBar, QPushButton, QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)

from src import config as cfg
from src import updater
from src.llm import KEY_HELP, PROVIDERS, SECRET_FOR_PROVIDER, create_provider
from src.llm.base import LLMError


class GoogleAuthLike(Protocol):
    """v0.3 gsync.auth 가 구현. 설정 화면은 이 인터페이스만 본다."""
    def is_logged_in(self) -> bool: ...
    def email(self) -> str: ...
    def login(self) -> str: ...        # 반환: 이메일
    def logout(self) -> None: ...
    def list_calendars(self) -> list[tuple[str, str]]: ...   # (id, name)
    def list_tasklists(self) -> list[tuple[str, str]]: ...


class _Task(QThread):
    """블로킹 호출을 백그라운드에서 실행하고 결과/오류를 시그널로 돌려준다."""
    done = Signal(object)
    error = Signal(str)

    def __init__(self, fn: Callable, parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self):
        try:
            self.done.emit(self._fn())
        except Exception as e:  # noqa: BLE001
            self.error.emit(str(e))


class _DownloadTask(QThread):
    """업데이트 산출물 다운로드 (진행률 시그널)."""
    progress = Signal(int, int)
    done = Signal(object)      # Path
    error = Signal(str)

    def __init__(self, info, parent=None):
        super().__init__(parent)
        self._info = info

    def run(self):
        try:
            self.done.emit(str(updater.download(self._info, lambda d, t: self.progress.emit(d, t))))
        except Exception as e:  # noqa: BLE001
            self.error.emit(str(e))


def default_coolm_dir() -> str:
    if platform.system() == "Windows":
        base = os.environ.get("LOCALAPPDATA", "")
        if base:
            return str(Path(base) / "CoolMessenger" / "Memo")
    return ""


class SettingsDialog(QDialog):
    saved = Signal(object)   # cfg.Config

    TAB_INDEX = {"llm": 0, "general": 1, "google": 2, "coolm": 3, "update": 4}

    def __init__(self, config: cfg.Config, google_auth: GoogleAuthLike | None = None, parent: QWidget | None = None,
                 *, initial_tab: str | None = None, update_info=None, quit_callback: Callable[[], None] | None = None):
        super().__init__(parent)
        self.config = config
        self.google = google_auth
        self._tasks: list[_Task] = []
        self._update_info = update_info
        self._update_archive = None
        self._quit = quit_callback or (lambda: QApplication.instance().quit())
        self.setWindowTitle("catmoa 설정")
        self.setMinimumWidth(560)

        tabs = self.tabs = QTabWidget()
        tabs.addTab(self._build_llm(), "LLM")
        tabs.addTab(self._build_general(), "일반")
        tabs.addTab(self._build_google(), "Google")
        tabs.addTab(self._build_coolm(), "쿨메신저")
        tabs.addTab(self._build_update(), "업데이트")
        if initial_tab in self.TAB_INDEX:
            tabs.setCurrentIndex(self.TAB_INDEX[initial_tab])

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("저장")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("취소")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addWidget(tabs)
        lay.addWidget(buttons)

    # ------------------------------------------------------------ LLM 탭
    def _build_llm(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        s = self.config.llm

        self.provider = QComboBox()
        for key, label in PROVIDERS.items():
            self.provider.addItem(label, key)
        self.provider.setCurrentIndex(max(0, list(PROVIDERS).index(s.provider) if s.provider in PROVIDERS else 0))
        self.provider.currentIndexChanged.connect(self._on_provider_changed)
        form.addRow("공급자", self.provider)

        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText("API 키")
        self.api_key_label = QLabel("API 키")
        form.addRow(self.api_key_label, self.api_key)

        self.ollama_url = QLineEdit(s.ollama_url)
        self.ollama_url_label = QLabel("Ollama 주소")
        form.addRow(self.ollama_url_label, self.ollama_url)

        row = QHBoxLayout()
        self.model = QComboBox()
        self.model.setEditable(True)
        self.model.setMinimumWidth(260)
        if s.model:
            self.model.addItem(s.model)
        self.btn_models = QPushButton("모델 목록 불러오기")
        self.btn_models.clicked.connect(self._load_models)
        row.addWidget(self.model, 1)
        row.addWidget(self.btn_models)
        form.addRow("모델", row)

        row2 = QHBoxLayout()
        self.btn_check = QPushButton("연결 테스트")
        self.btn_check.clicked.connect(self._check)
        self.check_result = QLabel("")
        self.check_result.setWordWrap(True)
        row2.addWidget(self.btn_check)
        row2.addWidget(self.check_result, 1)
        form.addRow("", row2)

        note = QLabel("입력한 문서·이미지·쪽지 내용이 선택한 공급자로 전송됩니다. "
                      "외부 전송이 걱정되면 Ollama(로컬)를 선택하세요. 이미지 분석에는 비전 지원 모델이 필요합니다 "
                      "(Solar는 Upstage 문서 인식(OCR)을 거쳐 이미지를 읽습니다).")
        note.setWordWrap(True)
        note.setStyleSheet("color: palette(mid); font-size: 11px;")
        form.addRow(note)

        self._on_provider_changed()
        return w

    def _current_provider_key(self) -> str:
        return self.provider.currentData()

    def _on_provider_changed(self, *_):
        key = self._current_provider_key()
        is_ollama = key == "ollama"
        self.api_key.setVisible(not is_ollama)
        self.api_key_label.setVisible(not is_ollama)
        self.ollama_url.setVisible(is_ollama)
        self.ollama_url_label.setVisible(is_ollama)
        if not is_ollama:
            self.api_key.setText(cfg.get_secret(SECRET_FOR_PROVIDER[key]) or "")
            self.api_key.setPlaceholderText(f"API 키 — 발급: {KEY_HELP.get(key, '')}")
        self.check_result.setText("")

    def _make_provider(self):
        key = self._current_provider_key()
        return create_provider(provider=key, model=self.model.currentText().strip(),
                               api_key=self.api_key.text().strip(), ollama_url=self.ollama_url.text().strip())

    def _run(self, fn: Callable, on_done: Callable, on_error: Callable):
        t = _Task(fn, self)
        t.done.connect(on_done)
        t.error.connect(on_error)
        t.finished.connect(lambda: self._tasks.remove(t) if t in self._tasks else None)
        self._tasks.append(t)
        t.start()

    def _load_models(self):
        self.btn_models.setEnabled(False)
        self.check_result.setText("모델 목록 조회 중…")
        try:
            p = self._make_provider()
        except LLMError as e:
            self.check_result.setText(f"❌ {e}")
            self.btn_models.setEnabled(True)
            return

        def done(models):
            cur = self.model.currentText().strip()
            self.model.clear()
            for m in models:
                tag = " (비전)" if m.vision else ""
                self.model.addItem(f"{m.id}{tag}", m.id)
            # 표시 텍스트에 태그가 붙으므로 실제 id는 itemData 로 관리
            idx = next((i for i in range(self.model.count()) if self.model.itemData(i) == cur), -1)
            self.model.setCurrentIndex(idx if idx >= 0 else 0)
            self.model.setEditText(self.model.itemData(self.model.currentIndex()) or cur)
            self.check_result.setText(f"모델 {len(models)}개")
            self.btn_models.setEnabled(True)

        def err(msg):
            self.check_result.setText(f"❌ {msg}")
            self.btn_models.setEnabled(True)

        self._run(p.list_models, done, err)

    def _check(self):
        self.btn_check.setEnabled(False)
        self.check_result.setText("테스트 중…")
        try:
            p = self._make_provider()
        except LLMError as e:
            self.check_result.setText(f"❌ {e}")
            self.btn_check.setEnabled(True)
            return

        def done(r):
            self.check_result.setText(("✅ " if r.ok else "❌ ") + r.message)
            self.btn_check.setEnabled(True)

        def err(msg):
            self.check_result.setText(f"❌ {msg}")
            self.btn_check.setEnabled(True)

        self._run(p.check, done, err)

    # ------------------------------------------------------------ 일반 탭
    def _build_general(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        s = self.config.schedule
        self.default_target = QComboBox()
        for key, label in (("auto", "AI가 제안 (일정/할 일 자동)"), ("calendar", "항상 📅 캘린더"), ("task", "항상 ✅ 태스크")):
            self.default_target.addItem(label, key)
        self.default_target.setCurrentIndex(("auto", "calendar", "task").index(s.default_target) if s.default_target in ("auto", "calendar", "task") else 0)
        form.addRow("기본 대상", self.default_target)

        self.alarm_enabled = QCheckBox("기본으로 알람 켜기")
        self.alarm_enabled.setChecked(s.alarm_enabled)
        form.addRow("알람", self.alarm_enabled)
        self.alarm_minutes = QSpinBox()
        self.alarm_minutes.setRange(0, 7 * 24 * 60)
        self.alarm_minutes.setSuffix("분 전")
        self.alarm_minutes.setValue(s.alarm_minutes)
        form.addRow("기본 알람 시간", self.alarm_minutes)
        self.task_alarm_as_event = QCheckBox("태스크 알람은 캘린더 알림 이벤트로 함께 생성 (Google Tasks는 알림을 지원하지 않음)")
        self.task_alarm_as_event.setChecked(s.task_alarm_as_event)
        form.addRow("", self.task_alarm_as_event)

        self.inbox_name = QLineEdit(s.inbox_list_name)
        form.addRow("인박스 태스크 목록명", self.inbox_name)
        self.complete_inbox = QCheckBox("인박스 항목을 등록한 뒤 원본을 완료 처리")
        self.complete_inbox.setChecked(s.complete_inbox_after_import)
        form.addRow("", self.complete_inbox)
        return w

    # ------------------------------------------------------------ Google 탭
    def _build_google(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self.google_status = QLabel()
        row = QHBoxLayout()
        self.btn_login = QPushButton("Google 로그인")
        self.btn_logout = QPushButton("로그아웃")
        self.btn_login.clicked.connect(self._google_login)
        self.btn_logout.clicked.connect(self._google_logout)
        row.addWidget(self.btn_login)
        row.addWidget(self.btn_logout)
        row.addStretch(1)
        form.addRow("계정", self.google_status)
        form.addRow("", row)

        self.calendar = QComboBox()
        self.tasklist = QComboBox()
        form.addRow("기본 캘린더", self.calendar)
        form.addRow("기본 태스크 목록", self.tasklist)
        self._refresh_google()
        return w

    def _refresh_google(self):
        g = self.google
        if g is None:
            self.google_status.setText("Google 연동 모듈이 아직 준비되지 않았습니다 (v0.3).")
            self.btn_login.setEnabled(False)
            self.btn_logout.setEnabled(False)
            return
        if g.is_logged_in():
            self.google_status.setText(f"✅ {g.email()}")
            self.btn_login.setEnabled(False)
            self.btn_logout.setEnabled(True)
            self._fill_google_lists()
        else:
            self.google_status.setText("로그인되지 않음")
            self.btn_login.setEnabled(True)
            self.btn_logout.setEnabled(False)

    def _fill_google_lists(self):
        def done(res):
            cals, lists = res
            self.calendar.clear()
            for cid, name in cals:
                self.calendar.addItem(name, cid)
            i = self.calendar.findData(self.config.schedule.calendar_id)
            self.calendar.setCurrentIndex(i if i >= 0 else 0)
            self.tasklist.clear()
            self.tasklist.addItem("(기본 목록)", "")
            for tid, name in lists:
                self.tasklist.addItem(name, tid)
            j = self.tasklist.findData(self.config.schedule.tasklist_id)
            self.tasklist.setCurrentIndex(j if j >= 0 else 0)

        self._run(lambda: (self.google.list_calendars(), self.google.list_tasklists()), done,
                  lambda m: self.google_status.setText(f"⚠ 목록 조회 실패: {m}"))

    def _google_login(self):
        self.btn_login.setEnabled(False)
        self.google_status.setText("브라우저에서 로그인을 완료하세요…")
        self._run(self.google.login, lambda _: self._refresh_google(),
                  lambda m: (self.google_status.setText(f"❌ {m}"), self.btn_login.setEnabled(True)))

    def _google_logout(self):
        self.google.logout()
        self.calendar.clear()
        self.tasklist.clear()
        self._refresh_google()

    # ------------------------------------------------------------ 쿨메신저 탭
    def _build_coolm(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        s = self.config.coolm
        self.coolm_enabled = QCheckBox("쿨메신저 새 쪽지를 자동으로 확인해 일정 분석 (Windows)")
        self.coolm_enabled.setChecked(s.enabled)
        lay.addWidget(self.coolm_enabled)

        box = QGroupBox()
        form = QFormLayout(box)
        self.coolm_poll = QSpinBox()
        self.coolm_poll.setRange(5, 3600)
        self.coolm_poll.setSuffix("초")
        self.coolm_poll.setValue(s.poll_seconds)
        form.addRow("확인 간격", self.coolm_poll)
        row = QHBoxLayout()
        self.coolm_dir = QLineEdit(s.memo_dir)
        self.coolm_dir.setPlaceholderText(default_coolm_dir() or "Memo 폴더 (예: %LOCALAPPDATA%\\CoolMessenger\\Memo)")
        b_auto = QPushButton("자동")
        b_auto.clicked.connect(lambda: self.coolm_dir.setText(default_coolm_dir()))
        b_browse = QPushButton("찾기…")
        b_browse.clicked.connect(self._browse_coolm)
        row.addWidget(self.coolm_dir, 1)
        row.addWidget(b_auto)
        row.addWidget(b_browse)
        form.addRow("메시지 폴더", row)
        self.coolm_skip = QCheckBox("처음 켤 때 기존 쪽지는 건너뛰기 (새 쪽지만 처리)")
        self.coolm_skip.setChecked(s.skip_existing_on_first_run)
        form.addRow("", self.coolm_skip)
        lay.addWidget(box)
        self.coolm_enabled.toggled.connect(box.setEnabled)
        box.setEnabled(s.enabled)

        note = QLabel("쪽지 DB는 읽기 전용 복사본으로만 접근하며 원본은 수정하지 않습니다. "
                      "다만 쪽지 <b>본문이 LLM으로 전송</b>됩니다 — 외부 전송이 걱정되면 LLM 탭에서 Ollama(로컬)를 선택하세요.")
        note.setWordWrap(True)
        note.setStyleSheet("color: palette(mid); font-size: 11px;")
        lay.addWidget(note)
        lay.addStretch(1)
        return w

    def _browse_coolm(self):
        d = QFileDialog.getExistingDirectory(self, "쿨메신저 Memo 폴더", self.coolm_dir.text() or default_coolm_dir())
        if d:
            self.coolm_dir.setText(d)

    # ------------------------------------------------------------ 업데이트 탭
    def _build_update(self) -> QWidget:
        from src import __version__

        w = QWidget()
        lay = QVBoxLayout(w)
        form = QFormLayout()
        form.addRow("현재 버전", QLabel(f"v{__version__}" + ("" if updater.is_frozen() else "  (소스 실행 중)")))
        self.update_status = QLabel("")
        self.update_status.setWordWrap(True)
        form.addRow("최신 버전", self.update_status)
        lay.addLayout(form)

        row = QHBoxLayout()
        self.btn_update_check = QPushButton("업데이트 확인")
        self.btn_update_check.clicked.connect(self._update_check)
        self.btn_update_install = QPushButton("업데이트 설치")
        self.btn_update_install.setEnabled(False)
        self.btn_update_install.clicked.connect(self._update_install)
        self.btn_update_page = QPushButton("릴리스 페이지 열기")
        self.btn_update_page.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(
            self._update_info.html_url if self._update_info else updater.RELEASES_PAGE)))
        row.addWidget(self.btn_update_check)
        row.addWidget(self.btn_update_install)
        row.addWidget(self.btn_update_page)
        row.addStretch(1)
        lay.addLayout(row)

        self.update_progress = QProgressBar()
        self.update_progress.setRange(0, 100)
        self.update_progress.hide()
        lay.addWidget(self.update_progress)

        self.update_notes = QPlainTextEdit()
        self.update_notes.setReadOnly(True)
        self.update_notes.setPlaceholderText("릴리스 노트")
        self.update_notes.setMaximumHeight(140)
        lay.addWidget(self.update_notes)

        self.update_check_on_start = QCheckBox("시작할 때 자동으로 업데이트 확인 (고양이 옆에 ⬆ 표시)")
        self.update_check_on_start.setChecked(self.config.update.check_on_start)
        lay.addWidget(self.update_check_on_start)
        lay.addStretch(1)

        if self._update_info:
            self._show_update_info(self._update_info)
        return w

    def _show_update_info(self, info):
        self._update_info = info
        if info is None:
            self.update_status.setText("✅ 최신 버전입니다.")
            self.btn_update_install.setEnabled(False)
            self.update_notes.setPlainText("")
            return
        self.update_status.setText(f"🆕 v{info.version} 사용 가능 ({info.asset_name})")
        self.update_notes.setPlainText(info.notes or "(릴리스 노트 없음)")
        self.btn_update_install.setEnabled(updater.is_frozen())
        if not updater.is_frozen():
            self.update_status.setText(self.update_status.text() + " — 소스 실행 중이라 자동 설치 불가, `git pull` 하세요")

    def _update_check(self):
        self.btn_update_check.setEnabled(False)
        self.update_status.setText("확인 중…")
        self._run(updater.check_latest,
                  lambda info: (self._show_update_info(info), self.btn_update_check.setEnabled(True)),
                  lambda m: (self.update_status.setText(f"❌ {m}"), self.btn_update_check.setEnabled(True)))

    def _update_install(self):
        info = self._update_info
        if not info:
            return
        self.btn_update_install.setEnabled(False)
        self.btn_update_check.setEnabled(False)
        self.update_progress.setValue(0)
        self.update_progress.show()
        self.update_status.setText(f"v{info.version} 내려받는 중…")
        t = _DownloadTask(info, self)
        t.progress.connect(lambda done, total: self.update_progress.setValue(int(done * 100 / total) if total else 0))
        t.done.connect(self._update_downloaded)
        t.error.connect(lambda m: (self.update_status.setText(f"❌ {m}"), self.update_progress.hide(),
                                   self.btn_update_install.setEnabled(True), self.btn_update_check.setEnabled(True)))
        t.finished.connect(lambda: self._tasks.remove(t) if t in self._tasks else None)
        self._tasks.append(t)
        t.start()

    def _update_downloaded(self, archive):
        self.update_status.setText("설치 준비 중… 앱이 종료된 뒤 새 버전으로 다시 실행됩니다.")
        try:
            updater.apply(Path(archive), self._quit)
        except updater.UpdateError as e:
            self.update_status.setText(f"❌ {e}")
            self.update_progress.hide()
            self.btn_update_install.setEnabled(True)
            self.btn_update_check.setEnabled(True)

    # ------------------------------------------------------------ 저장
    def _save(self):
        self.config.update.check_on_start = self.update_check_on_start.isChecked()
        c = self.config
        key = self._current_provider_key()
        c.llm.provider = key
        idx = self.model.currentIndex()
        data = self.model.itemData(idx) if idx >= 0 else None
        typed = self.model.currentText().strip()
        c.llm.model = data if (data and self.model.itemText(idx) == typed) else typed.split(" (")[0]
        c.llm.ollama_url = self.ollama_url.text().strip() or "http://localhost:11434"
        if key in SECRET_FOR_PROVIDER:
            secret = SECRET_FOR_PROVIDER[key]
            val = self.api_key.text().strip()
            if val:
                cfg.set_secret(secret, val)
            else:
                cfg.delete_secret(secret)

        s = c.schedule
        s.default_target = self.default_target.currentData()
        s.alarm_enabled = self.alarm_enabled.isChecked()
        s.alarm_minutes = self.alarm_minutes.value()
        s.task_alarm_as_event = self.task_alarm_as_event.isChecked()
        s.inbox_list_name = self.inbox_name.text().strip() or "인박스"
        s.complete_inbox_after_import = self.complete_inbox.isChecked()
        if self.calendar.count():
            s.calendar_id = self.calendar.currentData() or "primary"
        if self.tasklist.count():
            s.tasklist_id = self.tasklist.currentData() or ""

        cm = c.coolm
        cm.enabled = self.coolm_enabled.isChecked()
        cm.poll_seconds = self.coolm_poll.value()
        cm.memo_dir = self.coolm_dir.text().strip()
        cm.skip_existing_on_first_run = self.coolm_skip.isChecked()

        c.save()
        self.saved.emit(c)
        self.accept()
