"""OpenAI (ChatGPT) 어댑터."""
from __future__ import annotations

import base64
import re

from src.llm.base import LLMError, LLMProvider, LLMRequest, ModelInfo

DEFAULT_MODEL = "gpt-4o"

# 채팅에 쓸 수 없는 모델 제외 (임베딩, tts, whisper, dall-e, moderation, realtime, 이미지 생성 등)
_EXCLUDE_RE = re.compile(
    r"embedding|tts|whisper|dall-e|moderation|realtime|audio|transcribe|image|search|instruct|babbage|davinci|computer-use",
    re.I,
)
_VISION_RE = re.compile(r"^(gpt-4o|gpt-4\.1|gpt-4-turbo|gpt-5|o1(?!-mini)|o3|o4|chatgpt-4o)", re.I)


class OpenAIProvider(LLMProvider):
    name = "openai"
    supports_vision_default = None

    def __init__(self, api_key: str, model: str = "", client=None):
        super().__init__(model or DEFAULT_MODEL)
        if client is None:
            if not api_key:
                raise LLMError("OpenAI API 키가 없습니다. 설정에서 입력하세요.")
            import openai

            client = openai.OpenAI(api_key=api_key, max_retries=2, timeout=120.0)
        self.client = client

    def list_models(self) -> list[ModelInfo]:
        try:
            models = list(self.client.models.list())
        except Exception as e:  # noqa: BLE001
            raise LLMError(_friendly(e)) from e
        out = []
        for m in models:
            mid = m.id
            if not (mid.startswith("gpt") or mid.startswith("o") or mid.startswith("chatgpt")):
                continue
            if _EXCLUDE_RE.search(mid):
                continue
            out.append(ModelInfo(id=mid, vision=bool(_VISION_RE.match(mid))))
        out.sort(key=lambda m: m.id)
        return out

    def complete(self, req: LLMRequest) -> str:
        parts: list[dict] = [{"type": "text", "text": req.text}]
        for img in req.images:
            b64 = base64.standard_b64encode(img.data).decode("ascii")
            parts.append({"type": "image_url", "image_url": {"url": f"data:{img.mime};base64,{b64}"}})
        system = req.system
        kwargs: dict = {}
        if req.json_mode:
            system += "\n\nRespond with a single JSON value only."
            kwargs["response_format"] = {"type": "json_object"}
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": parts},
                ],
                max_completion_tokens=req.max_tokens,
                **kwargs,
            )
        except Exception as e:  # noqa: BLE001
            raise LLMError(_friendly(e)) from e
        choice = resp.choices[0]
        return choice.message.content or ""


def _friendly(e: Exception) -> str:
    try:
        import openai
    except ImportError:  # pragma: no cover
        return str(e)
    if isinstance(e, openai.AuthenticationError):
        return "OpenAI API 키가 올바르지 않습니다."
    if isinstance(e, openai.PermissionDeniedError):
        return "OpenAI API 키에 권한이 없습니다."
    if isinstance(e, openai.NotFoundError):
        return "선택한 OpenAI 모델을 찾을 수 없습니다."
    if isinstance(e, openai.RateLimitError):
        return "OpenAI 요청 한도를 초과했습니다 (또는 크레딧 부족)."
    if isinstance(e, openai.APIConnectionError):
        return "OpenAI 서버에 연결할 수 없습니다. 인터넷 연결을 확인하세요."
    if isinstance(e, openai.APIStatusError):
        return f"OpenAI API 오류 ({e.status_code}): {e.message}"
    return f"{type(e).__name__}: {e}"
