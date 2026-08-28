import json
import sys
from types import SimpleNamespace

import pytest

from src import config as cfg
from src.gsync.auth import SCOPES, GoogleAuth, GoogleAuthError


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("CATMOA_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("CATMOA_NO_KEYRING", "1")
    monkeypatch.delenv("CATMOA_GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("CATMOA_GOOGLE_CLIENT_SECRET", raising=False)
    monkeypatch.setattr(cfg, "_load_dotenv", lambda: {})
    monkeypatch.setitem(sys.modules, "src._secrets", None)  # 로컬 빌드 산출 src/_secrets.py 격리


def test_client_config_requires_id(monkeypatch):
    with pytest.raises(GoogleAuthError):
        GoogleAuth.client_config()
    monkeypatch.setenv("CATMOA_GOOGLE_CLIENT_ID", "abc.apps.googleusercontent.com")
    monkeypatch.setenv("CATMOA_GOOGLE_CLIENT_SECRET", "sec")
    c = GoogleAuth.client_config()["installed"]
    assert c["client_id"].startswith("abc") and c["client_secret"] == "sec"


def test_dotenv_fallback(monkeypatch):
    monkeypatch.setattr(cfg, "_load_dotenv", lambda: {"CATMOA_GOOGLE_CLIENT_ID": "from-dotenv", "CATMOA_GOOGLE_CLIENT_SECRET": "s"})
    assert cfg.google_client() == ("from-dotenv", "s")


def test_not_logged_in_initially():
    g = GoogleAuth()
    assert not g.is_logged_in() and g.email() == "" and g.credentials() is None
    with pytest.raises(GoogleAuthError):
        g.calendar_service()


class _FakeCreds:
    def __init__(self, token="tok", refresh="ref", valid=True, expired=False):
        self.token, self.refresh_token, self.valid, self.expired = token, refresh, valid, expired
        self.refreshed = False

    def to_json(self):
        # 실제 Credentials.to_json() 처럼 expiry 포함 (google-auth 2.57+는 expiry 없으면 즉시 만료 취급)
        return json.dumps({"token": self.token, "refresh_token": self.refresh_token,
                           "client_id": "x", "client_secret": "y", "token_uri": "https://oauth2.googleapis.com/token",
                           "expiry": "2099-01-01T00:00:00Z"})

    def refresh(self, _req):
        self.refreshed = True
        self.valid, self.expired = True, False


def test_login_saves_token_and_email(monkeypatch):
    monkeypatch.setenv("CATMOA_GOOGLE_CLIENT_ID", "id")
    fake = _FakeCreds()
    flow = SimpleNamespace(run_local_server=lambda **kw: fake)
    import google_auth_oauthlib.flow as f

    monkeypatch.setattr(f.InstalledAppFlow, "from_client_config", staticmethod(lambda conf, scopes: flow))
    monkeypatch.setattr(GoogleAuth, "_fetch_email", staticmethod(lambda creds: "t@school.kr"))
    g = GoogleAuth()
    assert g.login() == "t@school.kr"
    assert g.is_logged_in() and g.email() == "t@school.kr"
    stored = json.loads(cfg.get_secret(cfg.SECRET_GOOGLE_TOKEN))
    assert stored["_email"] == "t@school.kr" and stored["refresh_token"] == "ref"

    # 새 인스턴스가 저장된 토큰을 복원한다
    g2 = GoogleAuth()
    assert g2.is_logged_in() and g2.email() == "t@school.kr"
    assert g2.credentials() is not None


def test_refresh_expired(monkeypatch):
    fake = _FakeCreds(valid=False, expired=True)
    g = GoogleAuth()
    g._creds, g._loaded = fake, True
    import google.auth.transport.requests as r

    monkeypatch.setattr(r, "Request", lambda: None)
    assert g.credentials() is fake and fake.refreshed


def test_logout_clears(monkeypatch):
    g = GoogleAuth()
    g._creds, g._email, g._loaded = _FakeCreds(), "a@b", True
    g._save()
    import httpx

    monkeypatch.setattr(httpx, "post", lambda *a, **k: None)
    g.logout()
    assert not g.is_logged_in() and cfg.get_secret(cfg.SECRET_GOOGLE_TOKEN) is None


def test_scopes():
    assert any("calendar.events" in s for s in SCOPES) and any("/tasks" in s for s in SCOPES)
