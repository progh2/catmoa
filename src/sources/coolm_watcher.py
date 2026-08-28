"""쿨메신저 폴링 워처 (QTimer). 새 쪽지만 InputItem 으로 만들어 시그널로 내보낸다."""
from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QTimer, Signal

from src import config as cfg
from src.pipeline.items import InputItem
from src.sources.coolm import CoolmError, CoolmReader, Message, default_memo_dir

log = logging.getLogger(__name__)

MAX_PER_POLL = 20


def message_to_item(m: Message) -> InputItem:
    return InputItem(
        kind="coolm",
        payload=m.text,
        source_label=f"쿨메신저: {m.sender or '?'}" + (f" — {m.title[:20]}" if m.title.strip() else ""),
        reference_date=m.received.date(),          # "내일"은 받은 날 기준
        origin_ref=str(m.key),
    )


class CoolmWatcher(QObject):
    new_items = Signal(list)      # list[InputItem]
    error = Signal(str)           # 반복 오류는 한 번만
    status = Signal(str)          # 상태 문구 (툴팁 등)

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
        items = [message_to_item(m) for m in msgs if m.body.strip() or m.title.strip()]
        log.info("쿨메신저 새 쪽지 %d건 (키 %d 까지)", len(items), c.last_message_key)
        if items:
            self.new_items.emit(items)

    def _persist(self) -> None:
        try:
            self.config.save()
        except OSError as e:
            log.warning("쿨메신저 마지막 키 저장 실패: %s", e)
