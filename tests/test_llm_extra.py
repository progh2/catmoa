"""Gemini / Upstage 어댑터 — mock transport 로 요청 형식과 응답 처리 검증."""
import json
from types import SimpleNamespace

import httpx
import pytest

from src.llm import PROVIDERS, SECRET_FOR_PROVIDER, create_provider
from src.llm.base import ImageInput, LLMError, LLMRequest
from src.llm.gemini import GeminiProvider
from src.llm.upstage import UpstageProvider


# ---------------------------------------------------------------- Gemini

def _gemini_handler(request: httpx.Request) -> httpx.Response:
    assert request.headers.get("x-goog-api-key") == "gk"
    if request.url.path.endswith("/models"):
        return httpx.Response(200, json={"models": [
            {"name": "models/gemini-2.5-flash", "displayName": "Gemini 2.5 Flash", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/gemini-2.5-pro", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/text-embedding-004", "supportedGenerationMethods": ["embedContent"]},
            {"name": "models/imagen-3", "supportedGenerationMethods": ["generateContent"]},
        ]})
    if ":generateContent" in request.url.path:
        body = json.loads(request.content)
        assert body["generationConfig"]["responseMimeType"] == "application/json"
        assert body["system_instruction"]["parts"][0]["text"]
        parts = body["contents"][0]["parts"]
        n_img = sum(1 for p in parts if "inline_data" in p)
        if "bad-model" in request.url.path:
            return httpx.Response(404, json={"error": {"message": "not found"}})
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [
            {"text": json.dumps({"ok": True, "n_images": n_img})}]}}]})
    return httpx.Response(500, text="?")


def test_gemini_list_and_complete():
    p = GeminiProvider("gk", "gemini-2.5-flash", transport=httpx.MockTransport(_gemini_handler))
    ids = [m.id for m in p.list_models()]
    assert ids == ["gemini-2.5-pro", "gemini-2.5-flash"] and all(m.vision for m in p.list_models())
    out = p.complete(LLMRequest(system="s", text="t", images=[ImageInput(b"x", "image/jpeg")]))
    assert json.loads(out)["n_images"] == 1
    assert p.check().ok


def test_gemini_errors():
    p = GeminiProvider("gk", "bad-model", transport=httpx.MockTransport(_gemini_handler))
    with pytest.raises(LLMError, match="찾을 수 없습니다"):
        p.complete(LLMRequest(system="s", text="t"))

    def blocked(request):
        return httpx.Response(200, json={"candidates": [], "promptFeedback": {"blockReason": "SAFETY"}})
    p2 = GeminiProvider("gk", "m", transport=httpx.MockTransport(blocked))
    with pytest.raises(LLMError, match="SAFETY"):
        p2.complete(LLMRequest(system="s", text="t"))

    def badkey(request):
        return httpx.Response(400, json={"error": {"message": "API key not valid"}})
    p3 = GeminiProvider("gk", "m", transport=httpx.MockTransport(badkey))
    assert "올바르지" in p3.check().message


def test_gemini_requires_key():
    with pytest.raises(LLMError):
        GeminiProvider("")


# ---------------------------------------------------------------- Upstage

class _FakeUpstageChat:
    def __init__(self, ids):
        self.models = SimpleNamespace(list=lambda: [SimpleNamespace(id=i) for i in ids])
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))
        self.last = None

    def _create(self, **kw):
        self.last = kw
        user_text = kw["messages"][1]["content"][0]["text"]
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            content=json.dumps({"ok": True, "has_ocr": "[이미지 1 인식 결과]" in user_text})))])


def _upstage_ocr(request: httpx.Request) -> httpx.Response:
    assert request.url.path.endswith("/document-digitization")
    assert request.headers.get("authorization") == "Bearer uk"
    assert b'name="document"' in request.content and b"document-parse" in request.content
    return httpx.Response(200, json={"content": {"markdown": "# 회의\n9월 3일 14:00 회의실", "text": "..."}})


def test_upstage_models_and_ocr_path():
    chat = _FakeUpstageChat(["solar-pro2", "solar-mini", "solar-embedding-1-large", "other"])
    p = UpstageProvider("uk", client=chat, transport=httpx.MockTransport(_upstage_ocr))
    assert [m.id for m in p.list_models()] == ["solar-mini", "solar-pro2"]
    out = p.complete(LLMRequest(system="s", text="원문", images=[ImageInput(b"png")]))
    assert json.loads(out)["has_ocr"] is True
    assert chat.last["messages"][1]["content"][0]["text"].endswith("회의실")
    assert len(chat.last["messages"][1]["content"]) == 1      # 이미지 파트 없음 (OCR 텍스트로 대체)


def test_upstage_fallback_models_and_ocr_error():
    class Boom:
        models = SimpleNamespace(list=lambda: (_ for _ in ()).throw(RuntimeError("network")))
    p = UpstageProvider("uk", client=Boom(), transport=httpx.MockTransport(
        lambda r: httpx.Response(400, json={"error": {"message": "unsupported"}})))
    assert [m.id for m in p.list_models()] == ["solar-mini", "solar-pro2"]
    with pytest.raises(LLMError, match="문서 인식 실패"):
        p.complete(LLMRequest(system="s", text="t", images=[ImageInput(b"x")]))


def test_upstage_requires_key():
    with pytest.raises(LLMError):
        UpstageProvider("")


# ---------------------------------------------------------------- 팩토리/등록

def test_providers_registered(monkeypatch, tmp_path):
    monkeypatch.setenv("CATMOA_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("CATMOA_NO_KEYRING", "1")
    assert set(PROVIDERS) == {"claude", "openai", "gemini", "upstage", "ollama"}
    assert set(SECRET_FOR_PROVIDER) == {"claude", "openai", "gemini", "upstage"}
    assert isinstance(create_provider(provider="gemini", model="m", api_key="k"), GeminiProvider)
    assert isinstance(create_provider(provider="upstage", model="m", api_key="k"), UpstageProvider)
    for name in ("gemini", "upstage"):
        with pytest.raises(LLMError):
            create_provider(provider=name, model="m")   # 키 없음
