"""Google Gemini 어댑터 (generateContent REST, httpx — 추가 SDK 없음)."""
from __future__ import annotations

import base64
import re

import httpx

from src.llm.base import LLMError, LLMProvider, LLMRequest, ModelInfo

BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_MODEL = "gemini-2.5-flash"
_EXCLUDE_RE = re.compile(r"embedding|aqa|imagen|veo|tts|audio|image-generation|learnlm|gemma", re.I)


class GeminiProvider(LLMProvider):
    name = "gemini"
    supports_vision_default = True

    def __init__(self, api_key: str, model: str = "", transport=None):
        super().__init__(model or DEFAULT_MODEL)
        if not api_key and transport is None:
            raise LLMError("Gemini API 키가 없습니다. 설정에서 입력하세요. (https://aistudio.google.com/apikey)")
        self.api_key = api_key
        self._client = httpx.Client(base_url=BASE_URL, timeout=httpx.Timeout(180.0, connect=10.0),
                                    headers={"x-goog-api-key": api_key}, transport=transport)

    def _request(self, method: str, path: str, **kw) -> dict:
        try:
            r = self._client.request(method, path, **kw)
        except httpx.ConnectError as e:
            raise LLMError("Gemini 서버에 연결할 수 없습니다. 인터넷 연결을 확인하세요.") from e
        except httpx.HTTPError as e:
            raise LLMError(f"Gemini 통신 오류: {e}") from e
        if r.status_code >= 400:
            try:
                msg = r.json().get("error", {}).get("message", r.text)
            except ValueError:
                msg = r.text
            if r.status_code in (401, 403) or "API key" in msg or "API_KEY" in msg:
                raise LLMError("Gemini API 키가 올바르지 않습니다.")
            if r.status_code == 404:
                raise LLMError(f"선택한 Gemini 모델을 찾을 수 없습니다: {self.model}")
            if r.status_code == 429:
                raise LLMError("Gemini 요청 한도를 초과했습니다. 잠시 후 다시 시도하세요.")
            raise LLMError(f"Gemini API 오류 ({r.status_code}): {msg[:200]}")
        return r.json()

    def list_models(self) -> list[ModelInfo]:
        out: list[ModelInfo] = []
        token = None
        while True:
            params = {"pageSize": 200}
            if token:
                params["pageToken"] = token
            data = self._request("GET", "/models", params=params)
            for m in data.get("models", []):
                mid = m.get("name", "").removeprefix("models/")
                if not mid or "generateContent" not in m.get("supportedGenerationMethods", []):
                    continue
                if _EXCLUDE_RE.search(mid):
                    continue
                out.append(ModelInfo(id=mid, label=m.get("displayName") or mid, vision=True))
            token = data.get("nextPageToken")
            if not token:
                break
        out.sort(key=lambda m: m.id, reverse=True)
        return out

    def complete(self, req: LLMRequest) -> str:
        parts: list[dict] = []
        for img in req.images:
            parts.append({"inline_data": {"mime_type": img.mime,
                                          "data": base64.standard_b64encode(img.data).decode("ascii")}})
        parts.append({"text": req.text})
        body: dict = {
            "system_instruction": {"parts": [{"text": req.system}]},
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": req.max_tokens},
        }
        if req.json_mode:
            body["generationConfig"]["responseMimeType"] = "application/json"
        data = self._request("POST", f"/models/{self.model}:generateContent", json=body)
        cands = data.get("candidates") or []
        if not cands:
            reason = (data.get("promptFeedback") or {}).get("blockReason")
            raise LLMError(f"Gemini가 응답을 생성하지 않았습니다{f' (차단: {reason})' if reason else ''}.")
        parts_out = (cands[0].get("content") or {}).get("parts") or []
        return "".join(p.get("text", "") for p in parts_out if not p.get("thought"))
