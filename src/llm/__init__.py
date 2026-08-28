"""LLM 공급자 어댑터 (Claude / OpenAI / Gemini / Upstage / Ollama) + 팩토리."""
from __future__ import annotations

from src import config as cfg
from src.llm.base import CheckResult, ImageInput, LLMError, LLMProvider, LLMRequest, ModelInfo, extract_json

PROVIDERS = {
    "claude": "Claude (Anthropic)",
    "openai": "ChatGPT (OpenAI)",
    "gemini": "Gemini (Google)",
    "upstage": "Solar (Upstage)",
    "ollama": "Ollama (로컬)",
}

# 공급자별 API 키 keyring 이름 (없으면 키 불필요)
SECRET_FOR_PROVIDER = {
    "claude": cfg.SECRET_CLAUDE_API_KEY,
    "openai": cfg.SECRET_OPENAI_API_KEY,
    "gemini": cfg.SECRET_GEMINI_API_KEY,
    "upstage": cfg.SECRET_UPSTAGE_API_KEY,
}

KEY_HELP = {
    "claude": "https://console.anthropic.com/settings/keys",
    "openai": "https://platform.openai.com/api-keys",
    "gemini": "https://aistudio.google.com/apikey",
    "upstage": "https://console.upstage.ai/api-keys",
}


def create_provider(settings: cfg.LLMSettings | None = None, *, provider: str | None = None,
                    model: str | None = None, api_key: str | None = None,
                    ollama_url: str | None = None) -> LLMProvider:
    """설정(또는 명시 인자)으로 공급자 인스턴스를 만든다. API 키는 keyring에서 읽는다."""
    s = settings or cfg.Config.load().llm
    name = provider or s.provider
    mdl = model if model is not None else s.model
    if name == "ollama":
        from src.llm.ollama import OllamaProvider

        return OllamaProvider(base_url=ollama_url or s.ollama_url, model=mdl)
    if name not in SECRET_FOR_PROVIDER:
        raise LLMError(f"알 수 없는 LLM 공급자: {name}")
    key = api_key if api_key is not None else (cfg.get_secret(SECRET_FOR_PROVIDER[name]) or "")
    if name == "claude":
        from src.llm.claude import ClaudeProvider

        return ClaudeProvider(api_key=key, model=mdl)
    if name == "openai":
        from src.llm.openai_ import OpenAIProvider

        return OpenAIProvider(api_key=key, model=mdl)
    if name == "gemini":
        from src.llm.gemini import GeminiProvider

        return GeminiProvider(api_key=key, model=mdl)
    from src.llm.upstage import UpstageProvider

    return UpstageProvider(api_key=key, model=mdl)


__all__ = [
    "PROVIDERS", "SECRET_FOR_PROVIDER", "KEY_HELP", "create_provider", "CheckResult", "ImageInput", "LLMError",
    "LLMProvider", "LLMRequest", "ModelInfo", "extract_json",
]
