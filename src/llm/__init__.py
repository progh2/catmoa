"""LLM 공급자 어댑터 (Claude / OpenAI / Ollama) + 팩토리."""
from __future__ import annotations

from src import config as cfg
from src.llm.base import CheckResult, ImageInput, LLMError, LLMProvider, LLMRequest, ModelInfo, extract_json

PROVIDERS = {
    "claude": "Claude (Anthropic)",
    "openai": "ChatGPT (OpenAI)",
    "ollama": "Ollama (로컬)",
}


def create_provider(settings: cfg.LLMSettings | None = None, *, provider: str | None = None,
                    model: str | None = None, api_key: str | None = None,
                    ollama_url: str | None = None) -> LLMProvider:
    """설정(또는 명시 인자)으로 공급자 인스턴스를 만든다. API 키는 keyring에서 읽는다."""
    s = settings or cfg.Config.load().llm
    name = provider or s.provider
    mdl = model if model is not None else s.model
    if name == "claude":
        from src.llm.claude import ClaudeProvider

        key = api_key if api_key is not None else (cfg.get_secret(cfg.SECRET_CLAUDE_API_KEY) or "")
        return ClaudeProvider(api_key=key, model=mdl)
    if name == "openai":
        from src.llm.openai_ import OpenAIProvider

        key = api_key if api_key is not None else (cfg.get_secret(cfg.SECRET_OPENAI_API_KEY) or "")
        return OpenAIProvider(api_key=key, model=mdl)
    if name == "ollama":
        from src.llm.ollama import OllamaProvider

        return OllamaProvider(base_url=ollama_url or s.ollama_url, model=mdl)
    raise LLMError(f"알 수 없는 LLM 공급자: {name}")


__all__ = [
    "PROVIDERS", "create_provider", "CheckResult", "ImageInput", "LLMError",
    "LLMProvider", "LLMRequest", "ModelInfo", "extract_json",
]
