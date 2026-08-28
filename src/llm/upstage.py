"""Upstage Solar 어댑터.

- 채팅: OpenAI 호환 API (https://api.upstage.ai/v1) → OpenAIProvider 재사용
- 이미지: Solar 채팅 모델은 이미지를 받지 않으므로 Upstage Document Parse(OCR)로 텍스트화한 뒤 분석한다.
  한국어 문서 OCR 품질이 좋아 스캔 공문·스크린샷에 유리하다.
"""
from __future__ import annotations

import re

import httpx

from src.llm.base import ImageInput, LLMError, LLMRequest, ModelInfo
from src.llm.openai_ import OpenAIProvider

BASE_URL = "https://api.upstage.ai/v1"
DEFAULT_MODEL = "solar-pro2"
FALLBACK_MODELS = ["solar-pro2", "solar-mini"]
DOC_PARSE_MODEL = "document-parse"
_TAG_RE = re.compile(r"<[^>]+>")


class UpstageProvider(OpenAIProvider):
    name = "upstage"
    supports_vision_default = True   # OCR 경유

    def __init__(self, api_key: str, model: str = "", client=None, transport=None):
        if client is None:
            if not api_key:
                raise LLMError("Upstage API 키가 없습니다. 설정에서 입력하세요. (https://console.upstage.ai/api-keys)")
            import openai

            client = openai.OpenAI(api_key=api_key, base_url=BASE_URL, max_retries=2, timeout=120.0)
        super().__init__(api_key=api_key or "x", model=model or DEFAULT_MODEL, client=client)
        self.api_key = api_key
        self._http = httpx.Client(base_url=BASE_URL, timeout=httpx.Timeout(180.0, connect=10.0),
                                  headers={"Authorization": f"Bearer {api_key}"}, transport=transport)

    def list_models(self) -> list[ModelInfo]:
        try:
            models = list(self.client.models.list())
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            if "invalid_api_key" in msg or "401" in msg:
                raise LLMError("Upstage API 키가 올바르지 않습니다.") from e
            models = []
        ids = [m.id for m in models if "solar" in m.id.lower() and "embedding" not in m.id.lower()]
        if not ids:
            ids = FALLBACK_MODELS
        return [ModelInfo(id=i, label=f"{i}", vision=True) for i in sorted(set(ids))]

    # ---- 이미지 → OCR 텍스트
    def ocr_image(self, img: ImageInput) -> str:
        ext = "png" if "png" in img.mime else "jpg"
        try:
            r = self._http.post(
                "/document-digitization",
                files={"document": (f"image.{ext}", img.data, img.mime)},
                data={"model": DOC_PARSE_MODEL, "ocr": "force", "output_formats": '["text","markdown"]'},
            )
        except httpx.HTTPError as e:
            raise LLMError(f"Upstage 문서 인식 통신 오류: {e}") from e
        if r.status_code >= 400:
            try:
                msg = r.json().get("error", {}).get("message", r.text)
            except ValueError:
                msg = r.text
            raise LLMError(f"Upstage 문서 인식 실패 ({r.status_code}): {msg[:200]}")
        data = r.json()
        content = data.get("content") or {}
        text = content.get("markdown") or content.get("text") or _TAG_RE.sub(" ", content.get("html", ""))
        if not text.strip() and data.get("elements"):
            text = "\n".join(_TAG_RE.sub(" ", (e.get("content") or {}).get("html", "")) for e in data["elements"])
        return text.strip()

    def complete(self, req: LLMRequest) -> str:
        if req.images:
            ocr_blocks = []
            for i, img in enumerate(req.images, 1):
                t = self.ocr_image(img)
                if t:
                    ocr_blocks.append(f"[이미지 {i} 인식 결과]\n{t}")
            text = req.text
            if ocr_blocks:
                text += "\n\n" + "\n\n".join(ocr_blocks)
            req = LLMRequest(system=req.system, text=text, images=[], json_mode=req.json_mode, max_tokens=req.max_tokens)
        return super().complete(req)
