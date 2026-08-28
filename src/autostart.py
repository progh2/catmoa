"""운영체제 시작 시 자동 실행 등록/해제.

- macOS  : ~/Library/LaunchAgents/kr.catmoa.app.plist (RunAtLoad) — 시스템 설정 → 로그인 항목에 표시됨
- Windows: HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run\\catmoa
- Linux  : ~/.config/autostart/catmoa.desktop (XDG)
frozen(배포 빌드)이면 실행 파일 경로, 소스 실행이면 `python main.py` 를 등록한다.
"""
from __future__ import annotations

import os
import platform
import plistlib
import sys
from pathlib import Path

APP_ID = "kr.catmoa.app"


class AutostartError(Exception):
    pass


def launch_command() -> list[str]:
    """등록할 실행 명령. frozen 이면 실행 파일 하나, 아니면 python + main.py."""
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).resolve()
        if platform.system() == "Darwin":
            # .app 번들이면 번들 자체를 open 으로 실행 (Dock/권한 처리 일관)
            for p in exe.parents:
                if p.suffix == ".app":
                    return ["/usr/bin/open", "-a", str(p)]
        return [str(exe)]
    root = Path(__file__).resolve().parent.parent
    return [sys.executable, str(root / "main.py")]


# ---------------------------------------------------------------- 경로

def _plist_path() -> Path:
    return Path(os.environ.get("CATMOA_HOME", Path.home())) / "Library" / "LaunchAgents" / f"{APP_ID}.plist"


def _desktop_path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path(os.environ.get("CATMOA_HOME", Path.home())) / ".config")
    return base / "autostart" / "catmoa.desktop"


_WIN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


# ---------------------------------------------------------------- 공개 API

def is_enabled() -> bool:
    s = platform.system()
    try:
        if s == "Darwin":
            return _plist_path().exists()
        if s == "Windows":
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _WIN_KEY) as k:
                try:
                    winreg.QueryValueEx(k, "catmoa")
                    return True
                except FileNotFoundError:
                    return False
        return _desktop_path().exists()
    except OSError:
        return False


def enable() -> None:
    s = platform.system()
    cmd = launch_command()
    try:
        if s == "Darwin":
            p = _plist_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            data = {"Label": APP_ID, "ProgramArguments": cmd, "RunAtLoad": True, "ProcessType": "Interactive"}
            with open(p, "wb") as f:
                plistlib.dump(data, f)
        elif s == "Windows":
            import winreg

            value = " ".join(f'"{c}"' if " " in c else c for c in cmd)
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _WIN_KEY, 0, winreg.KEY_SET_VALUE) as k:
                winreg.SetValueEx(k, "catmoa", 0, winreg.REG_SZ, value)
        else:
            p = _desktop_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            exec_line = " ".join(f'"{c}"' if " " in c else c for c in cmd)
            p.write_text(
                "[Desktop Entry]\nType=Application\nName=catmoa\nComment=교사를 위한 일정 수집 고양이\n"
                f"Exec={exec_line}\nTerminal=false\nX-GNOME-Autostart-enabled=true\n",
                encoding="utf-8",
            )
    except OSError as e:
        raise AutostartError(f"자동 실행 등록 실패: {e}") from e


def disable() -> None:
    s = platform.system()
    try:
        if s == "Darwin":
            _plist_path().unlink(missing_ok=True)
        elif s == "Windows":
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _WIN_KEY, 0, winreg.KEY_SET_VALUE) as k:
                try:
                    winreg.DeleteValue(k, "catmoa")
                except FileNotFoundError:
                    pass
        else:
            _desktop_path().unlink(missing_ok=True)
    except OSError as e:
        raise AutostartError(f"자동 실행 해제 실패: {e}") from e


def set_enabled(on: bool) -> None:
    (enable if on else disable)()
