"""설정 저장/복원.

- 일반 설정: JSON 파일 (platformdirs 사용자 설정 디렉터리)
- 비밀값(API 키, Google 토큰): OS keyring, 실패 시 설정 디렉터리의 secrets.json 폴백

환경변수 `CATMOA_CONFIG_DIR` 로 설정 디렉터리를 바꿀 수 있다 (테스트/휴대용 실행).
"""
from __future__ import annotations

import json
import logging
import os
import stat
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, get_type_hints

from platformdirs import user_config_dir

log = logging.getLogger(__name__)

APP_NAME = "catmoa"


# ---------------------------------------------------------------- 경로

def config_dir() -> Path:
    override = os.environ.get("CATMOA_CONFIG_DIR")
    d = Path(override) if override else Path(user_config_dir(APP_NAME, appauthor=False))
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_path() -> Path:
    return config_dir() / "config.json"


# ---------------------------------------------------------------- 설정 모델

@dataclass
class LLMSettings:
    provider: str = "ollama"            # claude | openai | ollama
    model: str = ""
    ollama_url: str = "http://localhost:11434"


@dataclass
class ScheduleSettings:
    default_target: str = "auto"        # auto | calendar | task
    alarm_enabled: bool = True
    alarm_minutes: int = 30
    task_alarm_as_event: bool = True    # 태스크 알람 → 캘린더 알림 이벤트 생성
    calendar_id: str = "primary"
    tasklist_id: str = ""               # "" = 기본 목록
    inbox_list_name: str = "인박스"
    complete_inbox_after_import: bool = True


@dataclass
class CoolmSettings:
    enabled: bool = False
    poll_seconds: int = 30
    memo_dir: str = ""                  # "" = 자동 탐지
    skip_existing_on_first_run: bool = True
    last_message_key: int = 0


@dataclass
class UISettings:
    widget_x: int = -1                  # -1 = 화면 우하단 기본 위치
    widget_y: int = -1


@dataclass
class Config:
    llm: LLMSettings = field(default_factory=LLMSettings)
    schedule: ScheduleSettings = field(default_factory=ScheduleSettings)
    coolm: CoolmSettings = field(default_factory=CoolmSettings)
    ui: UISettings = field(default_factory=UISettings)
    version: int = 1

    # ---- 저장/복원
    def save(self, path: Path | None = None) -> Path:
        p = path or config_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(p)
        return p

    @classmethod
    def load(cls, path: Path | None = None) -> "Config":
        p = path or config_path()
        if not p.exists():
            return cls()
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            log.warning("설정 파일을 읽을 수 없어 기본값을 사용합니다: %s", e)
            return cls()
        return _from_dict(cls, data)


def _from_dict(cls: type, data: Any) -> Any:
    """알 수 없는 키는 무시하고, 누락된 키는 기본값으로 채운다 (버전 간 호환)."""
    if not is_dataclass(cls) or not isinstance(data, dict):
        return cls() if is_dataclass(cls) else data
    hints = get_type_hints(cls)  # `from __future__ import annotations` 로 문자열이 된 타입을 실제 타입으로 해석
    kwargs = {}
    for f in fields(cls):
        if f.name not in data:
            continue
        v = data[f.name]
        t = hints.get(f.name, f.type)
        kwargs[f.name] = _from_dict(t, v) if isinstance(t, type) and is_dataclass(t) else v
    try:
        return cls(**kwargs)
    except TypeError:
        return cls()


# ---------------------------------------------------------------- 비밀값

SECRET_CLAUDE_API_KEY = "claude_api_key"
SECRET_OPENAI_API_KEY = "openai_api_key"
SECRET_GOOGLE_TOKEN = "google_token"

_KEYRING_SERVICE = "catmoa"
_keyring_available: bool | None = None


def _fallback_path() -> Path:
    return config_dir() / "secrets.json"


def _read_fallback() -> dict[str, str]:
    p = _fallback_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_fallback(data: dict[str, str]) -> None:
    p = _fallback_path()
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    try:
        p.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def _keyring():
    """keyring 모듈을 지연 로드. 사용 불가면 None."""
    global _keyring_available
    if _keyring_available is False or os.environ.get("CATMOA_NO_KEYRING"):
        return None
    try:
        import keyring
        from keyring.errors import NoKeyringError  # noqa: F401
        _keyring_available = True
        return keyring
    except Exception:  # pragma: no cover - 환경 의존
        _keyring_available = False
        return None


def get_secret(name: str) -> str | None:
    kr = _keyring()
    if kr is not None:
        try:
            v = kr.get_password(_KEYRING_SERVICE, name)
            if v is not None:
                return v
        except Exception as e:
            log.info("keyring 조회 실패, 파일 폴백 사용: %s", e)
    return _read_fallback().get(name)


def set_secret(name: str, value: str) -> None:
    kr = _keyring()
    if kr is not None:
        try:
            kr.set_password(_KEYRING_SERVICE, name, value)
            # 폴백 파일에 남아있던 옛 값 제거
            fb = _read_fallback()
            if name in fb:
                fb.pop(name)
                _write_fallback(fb)
            return
        except Exception as e:
            log.warning("keyring 저장 실패, 파일 폴백 사용: %s", e)
    fb = _read_fallback()
    fb[name] = value
    _write_fallback(fb)


def delete_secret(name: str) -> None:
    kr = _keyring()
    if kr is not None:
        try:
            kr.delete_password(_KEYRING_SERVICE, name)
        except Exception:
            pass
    fb = _read_fallback()
    if name in fb:
        fb.pop(name)
        _write_fallback(fb)


# ---------------------------------------------------------------- 빌드 시 주입 비밀 (Google OAuth 클라이언트)

def google_client() -> tuple[str, str]:
    """(client_id, client_secret). 우선순위: 환경변수 > 빌드 시 생성된 src/_secrets.py > 빈 문자열."""
    cid = os.environ.get("CATMOA_GOOGLE_CLIENT_ID", "")
    csec = os.environ.get("CATMOA_GOOGLE_CLIENT_SECRET", "")
    if cid:
        return cid, csec
    try:
        from src import _secrets  # type: ignore

        return getattr(_secrets, "GOOGLE_CLIENT_ID", ""), getattr(_secrets, "GOOGLE_CLIENT_SECRET", "")
    except ImportError:
        return "", ""
