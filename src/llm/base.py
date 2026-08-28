"""LLM 공급자 공통 인터페이스.

모든 공급자는 세 가지를 제공한다:
- list_models(): 사용 가능한 모델 목록 (비전 지원 여부 포함)
- check(): 연결·모델 동작 테스트
- complete(): 텍스트(+이미지) 입력 → 텍스트 응답 (JSON 모드 권장)
"""
from __future__ import annotations

import json
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class LLMError(Exception):
    """사용자에게 보여줄 수 있는 메시지를 담은 LLM 오류."""


@dataclass
class ModelInfo:
    id: str
    label: str = ""
    vision: bool | None = None      # None = 알 수 없음

    def __post_init__(self):
        if not self.label:
            self.label = self.id


@dataclass
class ImageInput:
    data: bytes
    mime: str = "image/png"


@dataclass
class LLMRequest:
    system: str
    text: str
    images: list[ImageInput] = field(default_factory=list)
    json_mode: bool = True
    max_tokens: int = 4096


@dataclass
class CheckResult:
    ok: bool
    message: str
    latency_ms: int = 0
    model: str = ""


class LLMProvider(ABC):
    name: str = ""
    supports_vision_default: bool | None = None

    def __init__(self, model: str = ""):
        self.model = model

    @abstractmethod
    def list_models(self) -> list[ModelInfo]: ...

    @abstractmethod
    def complete(self, req: LLMRequest) -> str: ...

    def check(self) -> CheckResult:
        """짧은 JSON 프롬프트로 연결과 모델 동작을 확인한다."""
        if not self.model:
            return CheckResult(False, "모델을 선택하세요.")
        req = LLMRequest(
            system="You are a JSON API. Reply with exactly {\"ok\": true} and nothing else.",
            text="ping",
            max_tokens=64,
        )
        t0 = time.perf_counter()
        try:
            out = self.complete(req)
        except LLMError as e:
            return CheckResult(False, str(e), model=self.model)
        except Exception as e:  # noqa: BLE001 - 사용자에게 원인 표시
            return CheckResult(False, f"{type(e).__name__}: {e}", model=self.model)
        ms = int((time.perf_counter() - t0) * 1000)
        try:
            data = extract_json(out)
            if isinstance(data, dict) and data.get("ok") is True:
                return CheckResult(True, f"정상 ({ms}ms)", ms, self.model)
        except ValueError:
            pass
        return CheckResult(True, f"응답은 받았지만 형식이 예상과 다릅니다 ({ms}ms): {out[:80]!r}", ms, self.model)


# ---------------------------------------------------------------- JSON 유틸

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json(text: str):
    """LLM 응답에서 JSON을 꺼낸다. 코드펜스·앞뒤 잡담을 허용한다."""
    if not text:
        raise ValueError("빈 응답")
    candidates = [text.strip()]
    candidates += [m.strip() for m in _FENCE_RE.findall(text)]
    # 첫 { 또는 [ 부터 마지막 } 또는 ] 까지
    for open_c, close_c in (("{", "}"), ("[", "]")):
        i, j = text.find(open_c), text.rfind(close_c)
        if i != -1 and j > i:
            candidates.append(text[i:j + 1])
    for c in candidates:
        try:
            return json.loads(c)
        except json.JSONDecodeError:
            continue
    raise ValueError(f"JSON을 찾을 수 없습니다: {text[:120]!r}")
