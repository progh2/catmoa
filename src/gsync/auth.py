"""Google OAuth 로그인 (loopback flow) + 토큰 보관 + 서비스 팩토리.

- 클라이언트 ID/Secret은 빌드 시 내장(src/_secrets.py) 또는 환경변수/.env 에서 읽는다 → 사용자는 JSON 불필요
- refresh token 은 keyring(폴백: secrets.json)에 JSON 으로 저장
- 로그인은 브라우저를 열고 localhost 임시 포트로 콜백을 받는다
"""
from __future__ import annotations

import json
import logging
from typing import Any

from src import config as cfg

log = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/tasks",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]
_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
_REVOKE_URL = "https://oauth2.googleapis.com/revoke"

# google_auth_oauthlib 는 성공 메시지를 text/plain 으로 보내므로 HTML 이 아닌 일반 텍스트여야 한다
SUCCESS_HTML = "(=^◡ω◡^=)♪  catmoa 로그인 완료!  이 창을 닫고 앱으로 돌아가세요."


class GoogleAuthError(Exception):
    """사용자에게 보여줄 인증 오류."""


class GoogleAuth:
    """SettingsDialog 의 GoogleAuthLike 를 구현한다."""

    def __init__(self):
        self._creds: Any = None
        self._email: str = ""
        self._loaded = False

    # ------------------------------------------------------------ 클라이언트
    @staticmethod
    def client_config() -> dict:
        cid, csec = cfg.google_client()
        if not cid:
            raise GoogleAuthError(
                "이 빌드에는 Google 클라이언트 ID가 없습니다. "
                "개발 중이라면 .env 파일에 CATMOA_GOOGLE_CLIENT_ID / CATMOA_GOOGLE_CLIENT_SECRET 를 넣으세요."
            )
        return {
            "installed": {
                "client_id": cid,
                "client_secret": csec,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"],
            }
        }

    # ------------------------------------------------------------ 토큰 저장/복원
    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        raw = cfg.get_secret(cfg.SECRET_GOOGLE_TOKEN)
        if not raw:
            return
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return
        self._email = data.pop("_email", "")
        try:
            from google.oauth2.credentials import Credentials

            self._creds = Credentials.from_authorized_user_info(data, SCOPES)
        except Exception as e:  # noqa: BLE001
            log.warning("저장된 Google 토큰을 읽을 수 없습니다: %s", e)
            self._creds = None

    def _save(self) -> None:
        if self._creds is None:
            cfg.delete_secret(cfg.SECRET_GOOGLE_TOKEN)
            return
        data = json.loads(self._creds.to_json())
        data["_email"] = self._email
        cfg.set_secret(cfg.SECRET_GOOGLE_TOKEN, json.dumps(data))

    # ------------------------------------------------------------ 상태
    def credentials(self):
        """유효한 Credentials 를 돌려준다 (필요 시 refresh). 없으면 None."""
        self._load()
        c = self._creds
        if c is None:
            return None
        if c.valid:
            return c
        if c.expired and c.refresh_token:
            try:
                from google.auth.transport.requests import Request

                c.refresh(Request())
                self._save()
                return c
            except Exception as e:  # noqa: BLE001
                log.warning("Google 토큰 갱신 실패: %s", e)
                return None
        return None

    def is_logged_in(self) -> bool:
        self._load()
        c = self._creds
        return c is not None and (c.valid or bool(c.refresh_token))

    def email(self) -> str:
        self._load()
        return self._email

    # ------------------------------------------------------------ 로그인/로그아웃
    def login(self) -> str:
        from google_auth_oauthlib.flow import InstalledAppFlow

        flow = InstalledAppFlow.from_client_config(self.client_config(), SCOPES)
        try:
            creds = flow.run_local_server(
                port=0,
                open_browser=True,
                authorization_prompt_message="",
                success_message=SUCCESS_HTML,
                timeout_seconds=300,
            )
        except Exception as e:  # noqa: BLE001
            raise GoogleAuthError(f"로그인에 실패했습니다: {e}") from e
        self._creds = creds
        self._email = self._fetch_email(creds)
        self._save()
        log.info("Google 로그인: %s", self._email)
        return self._email

    def logout(self) -> None:
        self._load()
        c = self._creds
        if c is not None:
            try:
                import httpx

                httpx.post(_REVOKE_URL, params={"token": c.refresh_token or c.token}, timeout=5.0)
            except Exception:  # noqa: BLE001 - 취소 실패해도 로컬 토큰은 지운다
                pass
        self._creds = None
        self._email = ""
        self._save()

    @staticmethod
    def _fetch_email(creds) -> str:
        try:
            import httpx

            r = httpx.get(_USERINFO_URL, headers={"Authorization": f"Bearer {creds.token}"}, timeout=10.0)
            if r.status_code == 200:
                return r.json().get("email", "")
        except Exception as e:  # noqa: BLE001
            log.info("이메일 조회 실패: %s", e)
        return ""

    # ------------------------------------------------------------ 서비스
    def _service(self, name: str, version: str):
        creds = self.credentials()
        if creds is None:
            raise GoogleAuthError("Google에 로그인되어 있지 않습니다. 설정 → Google 에서 로그인하세요.")
        from googleapiclient.discovery import build

        return build(name, version, credentials=creds, cache_discovery=False)

    def calendar_service(self):
        return self._service("calendar", "v3")

    def tasks_service(self):
        return self._service("tasks", "v1")

    def list_calendars(self) -> list[tuple[str, str]]:
        svc = self.calendar_service()
        out: list[tuple[str, str]] = []
        page = None
        while True:
            resp = svc.calendarList().list(pageToken=page, minAccessRole="writer").execute()
            for c in resp.get("items", []):
                name = c.get("summaryOverride") or c.get("summary", c["id"])
                if c.get("primary"):
                    out.insert(0, ("primary", f"{name} (기본)"))
                else:
                    out.append((c["id"], name))
            page = resp.get("nextPageToken")
            if not page:
                break
        head, rest = out[:1] if out and out[0][0] == "primary" else [], out[1:] if out and out[0][0] == "primary" else out
        return head + sorted(rest, key=lambda x: x[1])

    def list_tasklists(self) -> list[tuple[str, str]]:
        svc = self.tasks_service()
        out: list[tuple[str, str]] = []
        page = None
        while True:
            resp = svc.tasklists().list(maxResults=100, pageToken=page).execute()
            for t in resp.get("items", []):
                out.append((t["id"], t.get("title", "")))
            page = resp.get("nextPageToken")
            if not page:
                break
        return out
