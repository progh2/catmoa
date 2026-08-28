"""Ollama 로컬 LLM 어댑터 (HTTP API)."""
from __future__ import annotations

import base64

import httpx

from src.llm.base import LLMError, LLMProvider, LLMRequest, ModelInfo

DEFAULT_URL = "http://localhost:11434"


class OllamaProvider(LLMProvider):
    name = "ollama"
    supports_vision_default = None

    def __init__(self, base_url: str = DEFAULT_URL, model: str = "", transport=None):
        super().__init__(model)
        self.base_url = (base_url or DEFAULT_URL).rstrip("/")
        self._client = httpx.Client(base_url=self.base_url, timeout=httpx.Timeout(300.0, connect=5.0),
                                    transport=transport)

    # ---- 내부
    def _get(self, path: str) -> dict:
        try:
            r = self._client.get(path)
            r.raise_for_status()
            return r.json()
        except httpx.ConnectError as e:
            raise LLMError(f"Ollama에 연결할 수 없습니다 ({self.base_url}). Ollama가 실행 중인지 확인하세요.") from e
        except httpx.HTTPStatusError as e:
            raise LLMError(f"Ollama 오류 ({e.response.status_code}): {e.response.text[:200]}") from e
        except httpx.HTTPError as e:
            raise LLMError(f"Ollama 통신 오류: {e}") from e

    def _post(self, path: str, body: dict) -> dict:
        try:
            r = self._client.post(path, json=body)
            r.raise_for_status()
            return r.json()
        except httpx.ConnectError as e:
            raise LLMError(f"Ollama에 연결할 수 없습니다 ({self.base_url}). Ollama가 실행 중인지 확인하세요.") from e
        except httpx.HTTPStatusError as e:
            msg = e.response.text[:200]
            if e.response.status_code == 404 and "not found" in msg:
                raise LLMError(f"Ollama에 모델 '{self.model}'이 없습니다. `ollama pull {self.model}` 후 다시 시도하세요.") from e
            raise LLMError(f"Ollama 오류 ({e.response.status_code}): {msg}") from e
        except httpx.HTTPError as e:
            raise LLMError(f"Ollama 통신 오류: {e}") from e

    # ---- 공개
    def list_models(self) -> list[ModelInfo]:
        data = self._get("/api/tags")
        out = []
        for m in data.get("models", []):
            name = m.get("name") or m.get("model")
            if not name:
                continue
            out.append(ModelInfo(id=name, vision=self._has_vision(name)))
        out.sort(key=lambda m: m.id)
        return out

    def _has_vision(self, name: str) -> bool | None:
        """/api/show 의 capabilities 로 비전 지원 여부 판단 (구버전 Ollama는 None)."""
        try:
            info = self._post("/api/show", {"model": name})
        except LLMError:
            return None
        caps = info.get("capabilities")
        if isinstance(caps, list):
            return "vision" in caps
        return None

    def complete(self, req: LLMRequest) -> str:
        user_msg: dict = {"role": "user", "content": req.text}
        if req.images:
            user_msg["images"] = [base64.standard_b64encode(i.data).decode("ascii") for i in req.images]
        body: dict = {
            "model": self.model,
            "messages": [{"role": "system", "content": req.system}, user_msg],
            "stream": False,
            # thinking 모델(gemma4, qwen3 등)은 사고 토큰이 num_predict를 다 써서 content가 비므로 끈다.
            # 비-thinking 모델도 이 필드를 무시하고 정상 응답한다.
            "think": False,
            "options": {"temperature": 0, "num_predict": req.max_tokens},
        }
        if req.json_mode:
            body["format"] = "json"
        data = self._post("/api/chat", body)
        return (data.get("message") or {}).get("content", "")
