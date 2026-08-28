"""쿨메신저 폴링 워처 (QTimer). 새 쪽지만 InputItem 으로 만들어 시그널로 내보낸다."""
from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QTimer, Signal

from src import config as cfg
from src.pipeline.items import InputItem
from src.sources.coolm import CoolmError, CoolmReader, Message, default_memo_dir

log = logging.getLogger(__name__)

MAX_PER_POLL = 20


def check_connection(memo_dir: str) -> str:
    """DB 를 열어 상태를 한 줄로 요약한다. 실패 시 CoolmError."""
    with CoolmReader(memo_dir) as r:
        latest = r.latest_messages(limit=1)
        total = r.latest_key()
        if latest:
            m = latest[0]
            return (f"✅ 연결 OK — 쪽지 키 최대 {total}, 최근: {m.received:%Y-%m-%d %H:%M} {m.sender or '?'}"
                    + (f" 「{m.title[:20]}」" if m.title.strip() else ""))
        return f"✅ 연결 OK — 받은 쪽지가 없습니다 (키 최대 {total})"


def message_to_item(m: Message, history_chars: int = 1200) -> InputItem:
    return InputItem(
        kind="coolm",
        payload=m.to_text(history_chars),
        source_label=f"쿨메신저: {m.sender or '?'}" + (f" — {m.title[:20]}" if m.title.strip() else ""),
        reference_date=m.received.date(),          # "내일"은 받은 날 기준
        origin_ref=str(m.key),
    )


class CoolmWatcher(QObject):
    new_items = Signal(list)      # list[InputItem]
    error = Signal(str)           # 반복 오류는 한 번만
    status = Signal(str)          # 상태 문구 (툴팁 등)
    polling = Signal()            # 폴링 시작 (고양이 '서류 찾는' 표정용)

    def __init__(self, config: cfg.Config, parent=None):
        super().__init__(parent)
        self.config = config
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.poll)
        self._last_error = ""
        self._first_run = True

    # ---- 제어
    def apply_config(self, config: cfg.Config | None = None) -> None:
        """설정이 바뀌면 호출. 사용 여부·간격을 즉시 반영한다."""
        if config is not None:
            self.config = config
        c = self.config.coolm
        if c.enabled:
            self._timer.start(max(5, int(c.poll_seconds)) * 1000)
            self.status.emit(f"쿨메신저 감시 중 ({c.poll_seconds}초)")
            if self._first_run:
                QTimer.singleShot(500, self.poll)
        else:
            self._timer.stop()
            self.status.emit("쿨메신저 감시 꺼짐")

    @property
    def active(self) -> bool:
        return self._timer.isActive()

    def memo_dir(self) -> str:
        return self.config.coolm.memo_dir or default_memo_dir()

    # ---- 폴링
    def poll(self) -> None:
        c = self.config.coolm
        if not c.enabled:
            return
        self.polling.emit()
        try:
            with CoolmReader(self.memo_dir()) as r:
                if self._first_run and c.skip_existing_on_first_run and c.last_message_key == 0:
                    c.last_message_key = r.latest_key()
                    self._first_run = False
                    self._persist()
                    log.info("쿨메신저 첫 실행: 기존 쪽지 %d 까지 건너뜀", c.last_message_key)
                    return
                self._first_run = False
                msgs = r.messages_after(c.last_message_key, limit=MAX_PER_POLL)
        except CoolmError as e:
            if str(e) != self._last_error:
                self._last_error = str(e)
                self.error.emit(str(e))
            return
        self._last_error = ""
        if not msgs:
            return
        c.last_message_key = max(m.key for m in msgs)
        self._persist()
        items = [message_to_item(m, c.history_chars) for m in msgs if m.body.strip() or m.title.strip()]
        log.info("쿨메신저 새 쪽지 %d건 (키 %d 까지)", len(items), c.last_message_key)
        if items:
            self.new_items.emit(items)

    # ---- 강제 조회 (설정 버튼 / 우클릭 메뉴). DB 읽기(fetch_now)는 어느 스레드에서든, deliver 는 메인 스레드에서.
    FORCE_INITIAL_LIMIT = 5

    def fetch_now(self, memo_dir: str | None = None) -> list[Message]:
        """사용 여부와 무관하게 새 쪽지를 읽는다. 아직 한 번도 처리한 적 없으면(키 0) 최근 안읽은 쪽지 최대 5건."""
        c = self.config.coolm
        with CoolmReader(memo_dir or self.memo_dir()) as r:
            if c.last_message_key == 0:
                latest = r.latest_messages(limit=20)
                unread = [m for m in latest if m.is_unread][: self.FORCE_INITIAL_LIMIT]
                msgs = unread or latest[:1]
                return sorted(msgs, key=lambda m: m.key)
            return r.messages_after(c.last_message_key, limit=MAX_PER_POLL)

    def deliver(self, msgs: list[Message]) -> int:
        """읽어온 쪽지를 큐에 넣고 마지막 키를 저장. 반환: 투입 건수."""
        if not msgs:
            return 0
        self._first_run = False
        c = self.config.coolm
        c.last_message_key = max(c.last_message_key, max(m.key for m in msgs))
        self._persist()
        items = [message_to_item(m, c.history_chars) for m in msgs if m.body.strip() or m.title.strip()]
        if items:
            self.new_items.emit(items)
        return len(items)

    def _persist(self) -> None:
        try:
            self.config.save()
        except OSError as e:
            log.warning("쿨메신저 마지막 키 저장 실패: %s", e)
