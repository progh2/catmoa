import os
import plistlib
import sys

import pytest

from src import autostart


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("CATMOA_HOME", str(tmp_path))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    return tmp_path


def test_launch_command_dev_mode(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    cmd = autostart.launch_command()
    assert cmd[0] == sys.executable and cmd[1].endswith("main.py")


def test_launch_command_frozen_mac_uses_open(monkeypatch, tmp_path):
    app = tmp_path / "catmoa.app" / "Contents" / "MacOS"
    app.mkdir(parents=True)
    exe = app / "catmoa"; exe.write_text("")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    monkeypatch.setattr(autostart.platform, "system", lambda: "Darwin")
    assert autostart.launch_command() == ["/usr/bin/open", "-a", str(tmp_path / "catmoa.app")]
    monkeypatch.setattr(autostart.platform, "system", lambda: "Windows")
    assert autostart.launch_command() == [str(exe)]


def test_mac_plist_roundtrip(home, monkeypatch):
    monkeypatch.setattr(autostart.platform, "system", lambda: "Darwin")
    assert not autostart.is_enabled()
    autostart.enable()
    p = home / "Library" / "LaunchAgents" / "kr.catmoa.app.plist"
    assert p.exists() and autostart.is_enabled()
    data = plistlib.loads(p.read_bytes())
    assert data["Label"] == "kr.catmoa.app" and data["RunAtLoad"] is True and data["ProgramArguments"][-1].endswith("main.py")
    autostart.disable()
    assert not p.exists() and not autostart.is_enabled()
    autostart.disable()      # 두 번 해제해도 오류 없음


def test_linux_desktop_roundtrip(home, monkeypatch):
    monkeypatch.setattr(autostart.platform, "system", lambda: "Linux")
    autostart.set_enabled(True)
    p = home / ".config" / "autostart" / "catmoa.desktop"
    txt = p.read_text(encoding="utf-8")
    assert autostart.is_enabled() and "[Desktop Entry]" in txt and "Exec=" in txt and "main.py" in txt
    autostart.set_enabled(False)
    assert not autostart.is_enabled()


def test_xdg_config_home_respected(tmp_path, monkeypatch):
    monkeypatch.setattr(autostart.platform, "system", lambda: "Linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    autostart.enable()
    assert (tmp_path / "xdg" / "autostart" / "catmoa.desktop").exists()
    autostart.disable()


@pytest.mark.skipif(os.name != "nt", reason="Windows 레지스트리")
def test_windows_registry_roundtrip():
    autostart.enable()
    assert autostart.is_enabled()
    autostart.disable()
    assert not autostart.is_enabled()
