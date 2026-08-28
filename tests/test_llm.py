import json
from types import SimpleNamespace

import httpx
import pytest

from src.llm import create_provider, extract_json
from src.llm.base import ImageInput, LLMError, LLMRequest
from src.llm.claude import ClaudeProvider
from src.llm.ollama import OllamaProvider
from src.llm.openai_ import OpenAIProvider


# ---------------------------------------------------------------- extract_json

@pytest.mark.parametrize("text,expected", [
    ('{"a": 1}', {"a": 1}),
    ('```json\n{"a": 1}\n```', {"a": 1}),
    ('Sure! Here it is:\n{"a": [1, 2]}\nHope it helps.', {"a": [1, 2]}),
    ('[{"x": 1}]', [{"x": 1}]),
])
def test_extract_json(text, expected):
    assert extract_json(text) == expected


def test_extract_json_fails():
    with pytest.raises(ValueError):
        extract_json("no json here")


# ---------------------------------------------------------------- Ollama (mock transport)

def _ollama_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/api/tags":
        return httpx.Response(200, json={"models": [{"name": "gemma4:e2b"}, {"name": "llama3.1:latest"}]})
    if request.url.path == "/api/show":
        name = json.loads(request.content)["model"]
        caps = ["completion", "vision"] if "gemma" in name else ["completion"]
        return httpx.Response(200, json={"capabilities": caps})
    if request.url.path == "/api/chat":
        body = json.loads(request.content)
        assert body["stream"] is False
        assert body["format"] == "json"
        imgs = body["messages"][1].get("images", [])
        return httpx.Response(200, json={"message": {"role": "assistant",
                                                     "content": json.dumps({"ok": True, "n_images": len(imgs)})}})
    return httpx.Response(404, text="model 'x' not found")


def test_ollama_list_models_with_vision():
    p = OllamaProvider(model="gemma4:e2b", transport=httpx.MockTransport(_ollama_handler))
    models = p.list_models()
    assert [m.id for m in models] == ["gemma4:e2b", "llama3.1:latest"]
    assert models[0].vision is True and models[1].vision is False


def test_ollama_complete_and_check():
    p = OllamaProvider(model="gemma4:e2b", transport=httpx.MockTransport(_ollama_handler))
    out = p.complete(LLMRequest(system="s", text="t", images=[ImageInput(b"\x89PNG")]))
    assert json.loads(out)["n_images"] == 1
    r = p.check()
    assert r.ok and r.model == "gemma4:e2b"


def test_ollama_connection_error():
    def boom(request):
        raise httpx.ConnectError("refused")
    p = OllamaProvider(model="x", transport=httpx.MockTransport(boom))
    r = p.check()
    assert not r.ok and "연결할 수 없습니다" in r.message


# ---------------------------------------------------------------- Claude (fake client)

class _FakeClaude:
    def __init__(self):
        self.models = SimpleNamespace(list=lambda: [SimpleNamespace(id="claude-opus-5", display_name="Claude Opus 5")])
        self.messages = SimpleNamespace(create=self._create)
        self.last = None

    def _create(self, **kw):
        self.last = kw
        return SimpleNamespace(stop_reason="end_turn",
                               content=[SimpleNamespace(type="text", text='{"ok": true}')])


def test_claude_provider():
    fake = _FakeClaude()
    p = ClaudeProvider(api_key="", model="claude-opus-5", client=fake)
    assert p.list_models()[0].vision is True
    p.complete(LLMRequest(system="s", text="hello", images=[ImageInput(b"img", "image/jpeg")]))
    content = fake.last["messages"][0]["content"]
    assert content[0]["type"] == "image" and content[0]["source"]["media_type"] == "image/jpeg"
    assert content[1]["text"] == "hello"
    assert "JSON" in fake.last["system"]
    assert p.check().ok


def test_claude_requires_key():
    with pytest.raises(LLMError):
        ClaudeProvider(api_key="")


# ---------------------------------------------------------------- OpenAI (fake client)

class _FakeOpenAI:
    def __init__(self):
        ids = ["gpt-4o", "gpt-4o-mini", "text-embedding-3-small", "whisper-1", "o3-mini", "gpt-image-1"]
        self.models = SimpleNamespace(list=lambda: [SimpleNamespace(id=i) for i in ids])
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))
        self.last = None

    def _create(self, **kw):
        self.last = kw
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))])


def test_openai_provider():
    fake = _FakeOpenAI()
    p = OpenAIProvider(api_key="", model="gpt-4o", client=fake)
    ids = [m.id for m in p.list_models()]
    assert ids == ["gpt-4o", "gpt-4o-mini", "o3-mini"]
    p.complete(LLMRequest(system="s", text="hi", images=[ImageInput(b"x")]))
    assert fake.last["response_format"] == {"type": "json_object"}
    assert fake.last["messages"][1]["content"][1]["type"] == "image_url"
    assert p.check().ok


# ---------------------------------------------------------------- 팩토리

def test_factory(monkeypatch, tmp_path):
    monkeypatch.setenv("CATMOA_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("CATMOA_NO_KEYRING", "1")
    p = create_provider(provider="ollama", model="m", ollama_url="http://x:1")
    assert isinstance(p, OllamaProvider) and p.base_url == "http://x:1"
    with pytest.raises(LLMError):
        create_provider(provider="claude", model="m")  # 키 없음
    p2 = create_provider(provider="claude", model="m", api_key="sk-x")
    assert isinstance(p2, ClaudeProvider)
    with pytest.raises(LLMError):
        create_provider(provider="nope")
