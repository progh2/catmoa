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


def test_coolm_disabled_on_non_windows(app, tmp_path, monkeypatch):
    import platform as _pl
    from src.ui import settings_dialog as sd
    monkeypatch.setenv("CATMOA_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(sd.platform, "system", lambda: "Darwin")
    c = cfg.Config()
    dlg = SettingsDialog(c)
    assert not dlg.coolm_enabled.isEnabled() and not dlg.coolm_enabled.isChecked()
    dlg.coolm_dir.setText("/tmp/memo")                  # 폴더를 지정하면 켤 수 있음
    assert dlg.coolm_enabled.isEnabled()
    dlg.coolm_enabled.setChecked(True)
    dlg.coolm_dir.setText("")                           # 지우면 자동으로 꺼짐
    assert not dlg.coolm_enabled.isChecked() and not dlg.coolm_enabled.isEnabled()
    from src.ui.main_window import _coolm_available
    import src.ui.main_window as mw
    monkeypatch.setattr(_pl, "system", lambda: "Darwin")
    assert not _coolm_available(cfg.Config())
    c2 = cfg.Config(); c2.coolm.memo_dir = "/tmp/memo"
    assert _coolm_available(c2)
    monkeypatch.setattr(_pl, "system", lambda: "Windows")
    assert _coolm_available(cfg.Config())


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


# ---------------------------------------------------------------- 우클릭 '지금 확인' (#52)

class _FakeCat:
    def __init__(self):
        self.flashes = []

    def flash(self, state, msg=""):
        self.flashes.append((state, msg))

    def show_error(self, msg):
        self.flashes.append(("error", msg))


class _FakeToast:
    def __init__(self):
        self.messages = []

    def show_message(self, msg, near=None, ms=3000):
        self.messages.append(msg)


class _Ctrl:
    """AppController.coolm_check_now 만 떼어 검증 (위젯/스레드 없이)."""
    coolm_check_now = None       # 아래에서 실제 함수를 붙인다

    def __init__(self, watcher):
        self.coolm = watcher
        self.cat = _FakeCat()
        self.toast = _FakeToast()
        self.settings_opened = []

    def open_settings(self, tab=None):
        self.settings_opened.append(tab)

    def _coolm_fail(self, msg):
        self.cat.show_error(msg)
        self.toast.messages.append(f"실패: {msg}")

    def _run_bg(self, fn, on_done, on_error):
        try:
            on_done(fn())
        except Exception as e:      # noqa: BLE001
            on_error(str(e))


def _ctrl(watcher):
    from src.ui.main_window import AppController
    c = _Ctrl(watcher)
    c.coolm_check_now = AppController.coolm_check_now.__get__(c)
    return c


def test_check_now_reads_new_messages(app, tmp_path, monkeypatch):
    """새 쪽지를 실제로 읽어 큐로 넘긴다 — 없으면 울상 대신 '없어요' 안내."""
    monkeypatch.setenv("CATMOA_CONFIG_DIR", str(tmp_path / "cfg"))
    path = create_fake_udb(tmp_path / "Memo", _msgs())
    c = cfg.Config()
    c.coolm.memo_dir = str(tmp_path / "Memo")
    w = CoolmWatcher(c)
    delivered = []
    w.new_items.connect(delivered.append)
    ctrl = _ctrl(w)

    ctrl.coolm_check_now()
    assert ctrl.cat.flashes[0][0] == "searching"
    assert len(delivered) == 1 and [i.source_label.split(":")[1].strip()[0] for i in delivered[0]] == ["B", "C"]

    ctrl.coolm_check_now()                                   # 더 없으면
    assert ctrl.cat.flashes[-1][0] == "empty" and "새 쪽지가 없어요" in ctrl.toast.messages[-1]

    append_fake_message(path, {"sender": "D", "body": "새 쪽지", "received": datetime(2026, 6, 9, 8)})
    ctrl.coolm_check_now()
    assert len(delivered) == 2 and delivered[1][0].source_label.startswith("쿨메신저: D")
    w.deleteLater()


def test_check_now_missing_folder_guides_to_settings(app, tmp_path, monkeypatch):
    """폴더가 없으면 울상(오류) 대신 안내 + 설정 열기 — 우클릭이 그냥 실패하던 문제(#52)."""
    monkeypatch.setenv("CATMOA_CONFIG_DIR", str(tmp_path / "cfg"))
    import src.ui.main_window as mw
    monkeypatch.setattr(mw.QTimer, "singleShot", lambda ms, fn: fn())
    c = cfg.Config()
    c.coolm.memo_dir = str(tmp_path / "없는폴더")
    ctrl = _ctrl(CoolmWatcher(c))
    ctrl.coolm_check_now()
    assert ctrl.cat.flashes == [("annoyed", "쿨메신저 폴더를 찾지 못했어요")]
    assert "설정 → 쿨메신저" in ctrl.toast.messages[0] and ctrl.settings_opened == ["coolm"]


def test_check_now_reports_db_error(app, tmp_path, monkeypatch):
    """폴더는 있는데 .udb 가 없으면 사유를 그대로 알려준다."""
    monkeypatch.setenv("CATMOA_CONFIG_DIR", str(tmp_path / "cfg"))
    (tmp_path / "Memo2").mkdir()
    c = cfg.Config()
    c.coolm.memo_dir = str(tmp_path / "Memo2")
    ctrl = _ctrl(CoolmWatcher(c))
    ctrl.coolm_check_now()
    assert any("찾을 수 없습니다" in m for m in ctrl.toast.messages)
