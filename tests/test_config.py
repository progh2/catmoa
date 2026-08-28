import json

import pytest

from src import config as cfg


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("CATMOA_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("CATMOA_NO_KEYRING", "1")
    monkeypatch.delenv("CATMOA_GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("CATMOA_GOOGLE_CLIENT_SECRET", raising=False)
    yield tmp_path


def test_defaults():
    c = cfg.Config()
    assert c.llm.provider == "ollama"
    assert c.schedule.alarm_minutes == 30
    assert c.coolm.enabled is False
    assert c.coolm.poll_seconds == 30
    assert c.schedule.inbox_list_name == "인박스"


def test_save_and_load_roundtrip(isolated_config):
    c = cfg.Config()
    c.llm.provider = "claude"
    c.llm.model = "claude-sonnet-4-5"
    c.schedule.alarm_minutes = 15
    c.coolm.enabled = True
    c.coolm.poll_seconds = 60
    c.ui.widget_x = 100
    p = c.save()
    assert p == isolated_config / "config.json"

    c2 = cfg.Config.load()
    assert c2.llm.provider == "claude"
    assert c2.llm.model == "claude-sonnet-4-5"
    assert c2.schedule.alarm_minutes == 15
    assert c2.coolm.enabled is True
    assert c2.coolm.poll_seconds == 60
    assert c2.ui.widget_x == 100


def test_load_missing_file_returns_defaults():
    assert cfg.Config.load().llm.provider == "ollama"


def test_load_ignores_unknown_and_fills_missing(isolated_config):
    (isolated_config / "config.json").write_text(json.dumps({
        "llm": {"provider": "openai", "future_key": 1},
        "unknown_section": {"a": 1},
    }), encoding="utf-8")
    c = cfg.Config.load()
    assert c.llm.provider == "openai"
    assert c.llm.ollama_url == "http://localhost:11434"
    assert c.schedule.alarm_minutes == 30


def test_load_corrupt_file_returns_defaults(isolated_config):
    (isolated_config / "config.json").write_text("{not json", encoding="utf-8")
    assert cfg.Config.load().llm.provider == "ollama"


def test_secrets_fallback_file(isolated_config):
    assert cfg.get_secret("claude_api_key") is None
    cfg.set_secret("claude_api_key", "sk-test")
    assert cfg.get_secret("claude_api_key") == "sk-test"
    assert (isolated_config / "secrets.json").exists()
    cfg.delete_secret("claude_api_key")
    assert cfg.get_secret("claude_api_key") is None


def test_google_client_from_env(monkeypatch):
    assert cfg.google_client() == ("", "")
    monkeypatch.setenv("CATMOA_GOOGLE_CLIENT_ID", "id123")
    monkeypatch.setenv("CATMOA_GOOGLE_CLIENT_SECRET", "sec")
    assert cfg.google_client() == ("id123", "sec")
