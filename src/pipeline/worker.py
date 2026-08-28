"""통합 처리 큐 워커.

모든 입력(InputItem)은 하나의 큐에 들어가고 QThread 하나가 순차 처리한다:
    파싱(thinking) → LLM 추출(eating) → result 시그널(메인 스레드에서 검토 다이얼로그)
공급자는 항목마다 팩토리로 새로 만들어 설정 변경이 즉시 반영되게 한다.
"""
from __future__ import annotations

import logging
import queue
from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QThread, Signal

from src.extract import ExtractionError, ExtractionResult, Extractor
from src.llm.base import LLMError, LLMProvider
from src.parsers import ParsedInput, ParseError, normalize_image, parse_file
from src.pipeline.items import InputItem

log = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    item: InputItem
    extraction: ExtractionResult


@dataclass
class PipelineFailure:
    item: InputItem
    message: str


def parse_item(item: InputItem) -> ParsedInput:
    if item.kind == "file":
        return parse_file(item.payload)
    if item.kind == "image":
        return ParsedInput(images=[normalize_image(item.payload)], source=item.source_label)
    if item.kind in ("text", "coolm", "inbox_task"):
        text = str(item.payload)
        if not text.strip():
            raise ParseError("빈 텍스트입니다.")
        return ParsedInput(text=text, source=item.source_label)
    raise ParseError(f"알 수 없는 입력 종류: {item.kind}")


class PipelineWorker(QThread):
    phase = Signal(str)                 # "thinking" | "eating"
    queue_size = Signal(int)            # 대기 중(처리 중 제외)
    result = Signal(object)             # PipelineResult
    failed = Signal(object)             # PipelineFailure
    idle = Signal()                     # 큐가 비었을 때

    def __init__(self, provider_factory: Callable[[], LLMProvider], parent=None,
                 options_factory: Callable[[], dict] | None = None):
        super().__init__(parent)
        self._factory = provider_factory
        self._options = options_factory      # Extractor.extract 키워드 인자 (분류 규칙, 카테고리 목록)
        self._q: queue.Queue[InputItem | None] = queue.Queue()
        self._pending = 0

    # ---- 공개 (메인 스레드에서 호출)
    def enqueue(self, items: list[InputItem]) -> None:
        for it in items:
            self._q.put(it)
        self.queue_size.emit(self._q.qsize())
        if not self.isRunning():
            self.start()

    def stop(self, wait_ms: int = 3000) -> None:
        self._q.put(None)
        self.wait(wait_ms)

    # ---- 워커 스레드
    def run(self) -> None:
        while True:
            item = self._q.get()
            if item is None:
                break
            self.queue_size.emit(self._q.qsize())
            self._process(item)
            if self._q.empty():
                self.idle.emit()

    def _process(self, item: InputItem) -> None:
        log.info("처리 시작: %s (%s)", item.short, item.kind)
        try:
            self.phase.emit("thinking")
            parsed = parse_item(item)
            self.phase.emit("eating")
            provider = self._factory()
            opts = self._options() if self._options else {}
            extraction = Extractor(provider).extract(parsed, item.reference_date, item.source_label, **opts)
            log.info("추출 완료: %s → %d건", item.short, len(extraction.items))
            self.result.emit(PipelineResult(item, extraction))
        except (ParseError, ExtractionError, LLMError) as e:
            log.warning("처리 실패: %s: %s", item.short, e)
            self.failed.emit(PipelineFailure(item, str(e)))
        except Exception as e:  # noqa: BLE001 - 워커 스레드가 죽으면 안 됨
            log.exception("예상치 못한 오류: %s", item.short)
            self.failed.emit(PipelineFailure(item, f"{type(e).__name__}: {e}"))
