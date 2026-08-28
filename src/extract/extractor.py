"""추출기: ParsedInput → ScheduleItem 목록."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

from pydantic import ValidationError

import re

from src.extract.prompts import REPAIR_PROMPT, REQUEST_RETRY_HINT, SYSTEM_PROMPT, user_prompt

# 요청·부탁·지시 표현 (날짜 없는 할 일 재요청 트리거)
_REQUEST_CUE_RE = re.compile(
    r"(해\s*주세요|해주세요|주시기\s*바랍니다|바랍니다|부탁|요망|제출|회신|확인\s*바|알려\s*주|작성해|참석\s*여부|협조|신청해|보내\s*주|제출해|입력해|등록해)"
)
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
    scope: str = "relevant"     # relevant | irrelevant | ambiguous (사용자 역할 기준)
    scope_reason: str = ""


class Extractor:
    def __init__(self, provider: LLMProvider):
        self.provider = provider

    def extract(self, parsed: ParsedInput, ref: date | None = None, source: str = "", *,
                kind_rules: str = "", category_rules: str = "",
                categories: list[str] | tuple[str, ...] = (),
                drop_before: date | None = None, persona: str = "", skip_irrelevant: bool = True,
                timetable: str = "", source_chars: int = 1500, mask_pii: bool = True) -> ExtractionResult:
        """drop_before: 이 날짜보다 앞선 항목은 버린다 (예: 쪽지 수신일 이전의 지나간 일정).
        persona: 사용자 역할. 주어지면 scope(관련성)를 판정하고, skip_irrelevant 면 무관한 내용은 항목을 비운다."""
        ref = ref or date.today()
        source = source or parsed.source
        warnings: list[str] = []
        prompt_opts = dict(kind_rules=kind_rules, category_rules=category_rules, categories=tuple(categories),
                           persona=persona, timetable=timetable)

        text = parsed.text or ""
        if len(text) > MAX_TEXT_CHARS:
            warnings.append(f"텍스트가 길어 앞 {MAX_TEXT_CHARS:,}자만 분석했습니다.")
            text = text[:MAX_TEXT_CHARS]
        images = [ImageInput(b) for b in parsed.images[:MAX_IMAGES]]
        if len(parsed.images) > MAX_IMAGES:
            warnings.append(f"이미지가 많아 앞 {MAX_IMAGES}장만 분석했습니다.")
        if images and self.provider.supports_vision_default is False:
            warnings.append("선택한 모델은 이미지를 지원하지 않을 수 있습니다.")

        # LLM 에 보내는 텍스트만 개인정보 마스킹 (원문 source_text 는 그대로). 토큰은 결과에서 복원.
        mapping: dict[str, str] = {}
        llm_text = text
        if mask_pii and text:
            from src.privacy import mask_text

            mr = mask_text(text)
            llm_text, mapping = mr.masked, mr.mapping
            if mr.count:
                log.info("PII 마스킹 %d곳 (%s)%s", mr.count, mr.summary(), " +모델" if mr.used_model else "")
                warnings.append(f"🔒 개인정보 {mr.count}곳을 가리고 AI에 보냈어요 ({mr.summary()})")
            if images:
                warnings.append("이미지 속 개인정보는 가릴 수 없어 그대로 전송됩니다.")

        req = LLMRequest(
            system=SYSTEM_PROMPT,
            text=user_prompt(llm_text, ref, source, has_images=bool(images), **prompt_opts),
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
        if not items and llm_text and _REQUEST_CUE_RE.search(llm_text):
            # 모델이 놓친 '날짜 없는 요청' — 요청 표현이 있으면 task 로 한 번 더 요청
            log.info("요청 표현 있음, task 추출 재요청")
            req3 = LLMRequest(system=SYSTEM_PROMPT, text=req.text + "\n\n" + REQUEST_RETRY_HINT,
                              images=images, json_mode=True, max_tokens=4096)
            try:
                raw2 = self._call(req3)
                data2 = extract_json(raw2)
                items2, _ = _to_items(data2, ref, source)
                if items2:
                    items, raw, data = items2, raw2, data2
            except (ExtractionError, ValueError) as e:
                log.info("재요청 실패(무시): %s", e)
        if skipped:
            warnings.append(f"날짜를 확정할 수 없는 항목 {skipped}개를 제외했습니다.")
        if drop_before is not None:
            past = [i for i in items if not i.undated and i.start.date() < drop_before]
            if past:
                items = [i for i in items if i.undated or i.start.date() >= drop_before]
                warnings.append(f"{drop_before:%m/%d} 이전의 지나간 항목 {len(past)}개를 제외했습니다: "
                                + ", ".join(i.title[:20] for i in past[:3]))

        # 마스킹 토큰이 결과에 남았으면 원문으로 복원 (제목·메모·장소·카테고리)
        if mapping:
            from src.privacy import restore_text

            for it in items:
                it.title = restore_text(it.title, mapping) or it.title
                it.notes = restore_text(it.notes, mapping)
                it.location = restore_text(it.location, mapping)

        # 원문 발췌를 항목에 실어 캘린더 설명/태스크 메모에서 참고할 수 있게
        if source_chars > 0:
            excerpt = text.strip()
            if not excerpt and images:
                excerpt = f"(이미지 {len(images)}장 입력)"
            if len(excerpt) > source_chars:
                excerpt = excerpt[:source_chars].rstrip() + "\n…(이하 생략)"
            for it in items:
                it.source_text = excerpt

        scope, reason = _scope_of(data) if persona.strip() else ("relevant", "")
        if scope == "irrelevant" and skip_irrelevant and items:
            warnings.append(f"내 업무와 무관한 내용으로 판단해 {len(items)}개 항목을 등록하지 않습니다: {reason or '(이유 없음)'}")
            items = []
        elif scope == "ambiguous" and items:
            warnings.append(f"내 업무와 관련 있는지 불확실합니다: {reason or '(이유 없음)'}")
        return ExtractionResult(items=items, warnings=warnings, raw_text=raw, scope=scope, scope_reason=reason)

    def _call(self, req: LLMRequest) -> str:
        try:
            return self.provider.complete(req)
        except LLMError as e:
            raise ExtractionError(str(e)) from e


def _scope_of(data) -> tuple[str, str]:
    if not isinstance(data, dict):
        return "relevant", ""
    scope = str(data.get("scope") or "relevant").strip().lower()
    if scope not in ("relevant", "irrelevant", "ambiguous"):
        scope = "relevant"
    return scope, str(data.get("scope_reason") or "").strip()[:200]


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
        key = (item.title, item.start, item.kind, item.undated)
        if key in seen:
            continue
        seen.add(key)
        items.append(item)
    items.sort(key=lambda i: (i.undated, i.start))     # 날짜 있는 것 먼저
    return items, skipped
