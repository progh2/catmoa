"""Anthropic Claude 어댑터 (anthropic SDK 1.x)."""
from __future__ import annotations

import base64

from src.llm.base import LLMError, LLMProvider, LLMRequest, ModelInfo

DEFAULT_MODEL = "claude-opus-5"


class ClaudeProvider(LLMProvider):
    name = "claude"
    supports_vision_default = True

    def __init__(self, api_key: str, model: str = "", client=None):
        super().__init__(model or DEFAULT_MODEL)
        if client is None:
            if not api_key:
                raise LLMError("Claude API 키가 없습니다. 설정에서 입력하세요.")
            import anthropic

            client = anthropic.Anthropic(api_key=api_key, max_retries=2, timeout=120.0)
        self.client = client

    def list_models(self) -> list[ModelInfo]:
        try:
            return [
                ModelInfo(id=m.id, label=getattr(m, "display_name", "") or m.id, vision=True)
                for m in self.client.models.list()
            ]
        except Exception as e:  # noqa: BLE001
            raise LLMError(_friendly(e)) from e

    def complete(self, req: LLMRequest) -> str:
        content: list[dict] = []
        for img in req.images:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": img.mime,
                    "data": base64.standard_b64encode(img.data).decode("ascii"),
                },
            })
        content.append({"type": "text", "text": req.text})
        system = req.system
        if req.json_mode:
            system += "\n\nRespond with a single JSON value only. No prose, no code fences."
        try:
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=req.max_tokens,
                system=system,
                messages=[{"role": "user", "content": content}],
            )
        except Exception as e:  # noqa: BLE001
            raise LLMError(_friendly(e)) from e
        if getattr(resp, "stop_reason", None) == "refusal":
            raise LLMError("모델이 요청을 거부했습니다.")
        return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")


def _friendly(e: Exception) -> str:
    try:
        import anthropic
    except ImportError:  # pragma: no cover
        return str(e)
    if isinstance(e, anthropic.AuthenticationError):
        return "Claude API 키가 올바르지 않습니다."
    if isinstance(e, anthropic.PermissionDeniedError):
        return "Claude API 키에 권한이 없습니다."
    if isinstance(e, anthropic.NotFoundError):
        return "선택한 Claude 모델을 찾을 수 없습니다."
    if isinstance(e, anthropic.RateLimitError):
        return "Claude 요청 한도를 초과했습니다. 잠시 후 다시 시도하세요."
    if isinstance(e, anthropic.APIConnectionError):
        return "Claude 서버에 연결할 수 없습니다. 인터넷 연결을 확인하세요."
    if isinstance(e, anthropic.APIStatusError):
        return f"Claude API 오류 ({e.status_code}): {e.message}"
    return f"{type(e).__name__}: {e}"
