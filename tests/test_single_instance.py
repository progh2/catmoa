"""중복 실행 방지 (#51)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from src import single_instance as si


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("CATMOA_CONFIG_DIR", str(tmp_path))


def test_no_lock_runs_and_writes_lock():
    assert si.read_lock() is None
    assert si.take_over("1.4.11") == "run"
    ex = si.read_lock()
    assert ex.pid == os.getpid() and ex.version == "1.4.11"
    # 내 잠금이므로 다시 호출해도 실행 (pid 가 나 자신)
    assert si.take_over("1.4.11") == "run"
    si.clear_lock()
    assert si.read_lock() is None


def test_stale_lock_is_ignored(monkeypatch):
    si.write_lock("1.0.0")
    monkeypatch.setattr(si, "pid_alive", lambda pid: False)
    monkeypatch.setattr(si, "read_lock", lambda: si.Existing(pid=999999, version="1.0.0"))
    assert si.take_over("1.4.11") == "run"


def test_same_or_newer_running_exits(monkeypatch, app):
    calls = []
    monkeypatch.setattr(si, "read_lock", lambda: si.Existing(pid=4242, version="1.4.11"))
    monkeypatch.setattr(si, "pid_alive", lambda pid: True)
    monkeypatch.setattr(si, "ping_show", lambda server=si.SERVER_NAME: calls.append(("show", server)) or True)
    assert si.take_over("1.4.11") == "exit" and calls == [("show", si.SERVER_NAME)]
    calls.clear()
    assert si.take_over("1.4.0") == "exit" and calls           # 떠 있는 게 더 최신이어도 양보


def test_older_running_is_killed_and_taken_over(monkeypatch, app):
    calls = []
    monkeypatch.setattr(si, "read_lock", lambda: si.Existing(pid=4242, version="1.4.9"))
    monkeypatch.setattr(si, "pid_alive", lambda pid: True)
    monkeypatch.setattr(si, "ping_quit", lambda server=si.SERVER_NAME: calls.append("quit") or True)
    monkeypatch.setattr(si, "terminate", lambda pid, timeout=8.0: calls.append(("kill", pid)) or True)
    monkeypatch.setattr(si.time, "sleep", lambda s: None)
    assert si.take_over("1.4.11") == "run"
    assert calls == ["quit", ("kill", 4242)]
    import json
    assert json.loads(si.lock_path().read_text())["pid"] == os.getpid()   # 잠금은 새 프로세스 것


def test_pid_alive_self_and_missing():
    assert si.pid_alive(os.getpid())
    assert not si.pid_alive(0) and not si.pid_alive(-1)


def test_server_dispatches_show_and_quit(app, monkeypatch):
    got = []
    srv = si.InstanceServer(on_show=lambda: got.append("show"), on_quit=lambda: got.append("quit"),
                            name="catmoa-test-instance")
    assert srv.ok
    try:
        assert si.ping_show("catmoa-test-instance")
        for _ in range(50):
            app.processEvents()
            if got:
                break
        assert got == ["show"]
        assert si.ping_quit("catmoa-test-instance")
        for _ in range(50):
            app.processEvents()
            if len(got) > 1:
                break
        assert got == ["show", "quit"]
    finally:
        srv.close()


def test_clear_lock_keeps_other_owners():
    si.write_lock("1.4.11")
    path = si.lock_path()
    path.write_text('{"pid": 999999, "version": "1.4.11"}', encoding="utf-8")
    si.clear_lock()
    assert path.exists()                       # 남의 잠금은 지우지 않는다
