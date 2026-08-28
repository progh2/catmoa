import os
from datetime import datetime

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from src import config as cfg
from src.sources.coolm import CoolmError, append_fake_message, create_fake_udb
from src.sources.coolm_watcher import CoolmWatcher, check_connection
from src.ui.settings_dialog import SettingsDialog


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _msgs():
    return [
        {"sender": "A", "body": "옛 쪽지", "received": datetime(2026, 6, 1, 9), "unread": False},
        {"sender": "B", "title": "회의", "body": "내일 3시 회의", "received": datetime(2026, 6, 8, 9), "unread": True},
        {"sender": "C", "body": "6/12까지 제출", "received": datetime(2026, 6, 8, 10), "unread": True},
    ]


def test_check_connection(tmp_path):
    create_fake_udb(tmp_path, _msgs())
    s = check_connection(str(tmp_path))
    assert s.startswith("✅") and "C" in s and "2026-06-08 10:00" in s
    with pytest.raises(CoolmError):
        check_connection(str(tmp_path / "nope"))


def test_fetch_now_initial_unread_then_after_key(app, tmp_path, monkeypatch):
    monkeypatch.setenv("CATMOA_CONFIG_DIR", str(tmp_path / "cfg"))
    path = create_fake_udb(tmp_path / "Memo", _msgs())
    c = cfg.Config()
    c.coolm.enabled = False                      # 사용 안 함 상태에서도 강제 확인은 동작
    c.coolm.memo_dir = str(tmp_path / "Memo")
    w = CoolmWatcher(c)
    got = []
    w.new_items.connect(got.append)

    msgs = w.fetch_now()                          # 키 0 → 안읽은 쪽지만
    assert [m.sender for m in msgs] == ["B", "C"]
    assert w.deliver(msgs) == 2 and c.coolm.last_message_key == 3
    assert len(got) == 1 and got[0][0].source_label.startswith("쿨메신저: B")

    assert w.fetch_now() == [] and w.deliver([]) == 0
    append_fake_message(path, {"sender": "D", "body": "새 쪽지", "received": datetime(2026, 6, 9, 8)})
    msgs = w.fetch_now()
    assert [m.sender for m in msgs] == ["D"] and w.deliver(msgs) == 1 and c.coolm.last_message_key == 4
    w.deleteLater()


def test_default_memo_dir_scans_candidates(tmp_path, monkeypatch):
    from src.sources.coolm import default_memo_dir
    for v in ("LOCALAPPDATA", "APPDATA", "PROGRAMDATA", "USERPROFILE"):
        monkeypatch.delenv(v, raising=False)
    assert default_memo_dir() == ""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    # 관례 경로에 없고 APPDATA 쪽 계정별 하위 폴더에 udb 가 있는 경우
    create_fake_udb(tmp_path / "roaming" / "CoolMessenger" / "Memo" / "user01", _msgs())
    assert default_memo_dir() == str(tmp_path / "roaming" / "CoolMessenger" / "Memo" / "user01")
    # 관례 경로에 생기면 그쪽 우선
    create_fake_udb(tmp_path / "local" / "CoolMessenger" / "Memo", _msgs())
    assert default_memo_dir() == str(tmp_path / "local" / "CoolMessenger" / "Memo")


def test_settings_buttons_exist(app, tmp_path, monkeypatch):
    monkeypatch.setenv("CATMOA_CONFIG_DIR", str(tmp_path))
    create_fake_udb(tmp_path / "Memo", _msgs())
    c = cfg.Config()
    c.coolm.memo_dir = str(tmp_path / "Memo")
    w = CoolmWatcher(c)
    dlg = SettingsDialog(c, coolm_watcher=w)
    assert dlg.btn_coolm_now.isEnabled() and dlg.btn_coolm_test.isEnabled()
    dlg2 = SettingsDialog(c)                      # 워처 없으면 '지금 확인' 비활성
    assert not dlg2.btn_coolm_now.isEnabled()
    w.deleteLater()
