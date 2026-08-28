"""추출기: ParsedInput → ScheduleItem 목록."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

from pydantic import ValidationError

from src.extract.prompts import REPAIR_PROMPT, SYSTEM_PROMPT, user_prompt
from src.extract.schema import RawItem, ScheduleItem, normalize
from src.llm.base import ImageInput, LLMError, LLMProvider, LLMRequest, extract_json
from src.parsers import ParsedInput

log = logging.getLogger(__name__)

MAX_TEXT_CHARS = 40_000       # 이보다 길면 앞부분만 (공문은 보통 수천 자)
MAX_IMAGES = 10


class ExtractionError(Exception):
    """사용자에게 보여줄 추출 실패 사유."""


@dataclass
class ExtractionResult:
    items: list[ScheduleItem]
    warnings: list[str] = field(default_factory=list)
    raw_text: str = ""          # LLM 원 응답 (디버그)


class Extractor:
    def __init__(self, provider: LLMProvider):
        self.provider = provider

    def extract(self, parsed: ParsedInput, ref: date | None = None, source: str = "") -> ExtractionResult:
        ref = ref or date.today()
        source = source or parsed.source
        warnings: list[str] = []

        text = parsed.text or ""
        if len(text) > MAX_TEXT_CHARS:
            warnings.append(f"텍스트가 길어 앞 {MAX_TEXT_CHARS:,}자만 분석했습니다.")
            text = text[:MAX_TEXT_CHARS]
        images = [ImageInput(b) for b in parsed.images[:MAX_IMAGES]]
        if len(parsed.images) > MAX_IMAGES:
            warnings.append(f"이미지가 많아 앞 {MAX_IMAGES}장만 분석했습니다.")
        if images and self.provider.supports_vision_default is False:
            warnings.append("선택한 모델은 이미지를 지원하지 않을 수 있습니다.")

        req = LLMRequest(
            system=SYSTEM_PROMPT,
            text=user_prompt(text, ref, source, has_images=bool(images)),
            images=images,
            json_mode=True,
            max_tokens=4096,
        )
        raw = self._call(req)
        try:
            data = extract_json(raw)
        except ValueError:
            log.info("JSON 파싱 실패, 1회 재요청")
            req2 = LLMRequest(system=SYSTEM_PROMPT, text=req.text + "\n\n" + REPAIR_PROMPT,
                              images=images, json_mode=True, max_tokens=4096)
            raw = self._call(req2)
            try:
                data = extract_json(raw)
            except ValueError as e:
                raise ExtractionError(f"모델 응답을 해석할 수 없습니다: {e}") from e

        items, skipped = _to_items(data, ref, source)
        if skipped:
            warnings.append(f"날짜를 확정할 수 없는 항목 {skipped}개를 제외했습니다.")
        return ExtractionResult(items=items, warnings=warnings, raw_text=raw)

    def _call(self, req: LLMRequest) -> str:
        try:
            return self.provider.complete(req)
        except LLMError as e:
            raise ExtractionError(str(e)) from e


def _to_items(data, ref: date, source: str) -> tuple[list[ScheduleItem], int]:
    if isinstance(data, dict):
        rows = data.get("items") or data.get("schedules") or data.get("events") or []
        if not rows and any(k in data for k in ("title", "date")):
            rows = [data]
    elif isinstance(data, list):
        rows = data
    else:
        rows = []
    items: list[ScheduleItem] = []
    skipped = 0
    seen: set[tuple] = set()
    for r in rows:
        if not isinstance(r, dict):
            skipped += 1
            continue
        try:
            raw = RawItem(**{k: v for k, v in r.items() if k in RawItem.model_fields})
        except ValidationError:
            skipped += 1
            continue
        item = normalize(raw, ref, source)
        if item is None:
            skipped += 1
            continue
        key = (item.title, item.start, item.kind)
        if key in seen:
            continue
        seen.add(key)
        items.append(item)
    items.sort(key=lambda i: i.start)
    return items, skipped
