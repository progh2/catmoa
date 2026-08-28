"""자동 업데이트.

1. GitHub Releases `latest` 조회 → 현재 버전보다 새로우면 UpdateInfo
2. OS/아키텍처에 맞는 산출물 다운로드 (진행률 콜백)
3. 압축 해제 후, 앱 종료를 기다렸다가 설치 폴더를 교체하고 재실행하는 스크립트를 띄운다
   (실행 중인 바이너리는 스스로 덮어쓸 수 없으므로 외부 스크립트가 처리)

PyInstaller 로 얼린(frozen) 실행 파일에서만 설치가 가능하다. 소스 실행 중이면 안내만 한다.
"""
from __future__ import annotations

import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import httpx

from src import __version__

log = logging.getLogger(__name__)

REPO = "progh2/catmoa"
LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"


class UpdateError(Exception):
    pass


@dataclass
class UpdateInfo:
    version: str          # "1.2.0"
    tag: str              # "v1.2.0"
    notes: str
    html_url: str
    asset_name: str
    asset_url: str
    asset_size: int = 0


# ---------------------------------------------------------------- 버전/플랫폼

def parse_version(s: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", s or "")
    return tuple(int(n) for n in nums[:3]) or (0,)


def is_newer(candidate: str, current: str = __version__) -> bool:
    return parse_version(candidate) > parse_version(current)


def platform_key() -> tuple[str, str]:
    sysname = platform.system()
    arch = platform.machine().lower()
    arch = {"amd64": "x86_64", "x86_64": "x86_64", "arm64": "arm64", "aarch64": "arm64"}.get(arch, arch)
    name = {"Darwin": "macos", "Windows": "windows"}.get(sysname, "linux")
    return name, arch


def asset_name_for_platform() -> str:
    name, arch = platform_key()
    ext = "tar.gz" if name == "linux" else "zip"
    return f"catmoa-{name}-{arch}.{ext}"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def install_root() -> Path:
    """교체 대상: macOS 는 .app 번들, 그 외는 onedir 폴더."""
    exe = Path(sys.executable).resolve()
    if platform.system() == "Darwin":
        for p in exe.parents:
            if p.suffix == ".app":
                return p
    return exe.parent


# ---------------------------------------------------------------- 조회

def check_latest(transport=None, timeout: float = 10.0) -> UpdateInfo | None:
    """새 버전이 있으면 UpdateInfo, 최신이면 None. 네트워크 오류는 UpdateError."""
    try:
        with httpx.Client(timeout=timeout, transport=transport, follow_redirects=True,
                          headers={"Accept": "application/vnd.github+json", "User-Agent": f"catmoa/{__version__}"}) as c:
            r = c.get(LATEST_URL)
    except httpx.HTTPError as e:
        raise UpdateError(f"업데이트 서버에 연결할 수 없습니다: {e}") from e
    if r.status_code == 404:
        return None
    if r.status_code >= 400:
        raise UpdateError(f"업데이트 확인 실패 ({r.status_code})")
    data = r.json()
    tag = data.get("tag_name", "")
    version = tag.lstrip("vV")
    if not is_newer(version):
        return None
    want = asset_name_for_platform()
    asset = next((a for a in data.get("assets", []) if a.get("name") == want), None)
    if asset is None:
        raise UpdateError(f"새 버전 {tag} 이 있지만 이 OS용 파일({want})이 아직 없습니다. {RELEASES_PAGE}")
    return UpdateInfo(version=version, tag=tag, notes=(data.get("body") or "").strip(),
                      html_url=data.get("html_url", RELEASES_PAGE), asset_name=asset["name"],
                      asset_url=asset["browser_download_url"], asset_size=int(asset.get("size") or 0))


# ---------------------------------------------------------------- 다운로드/해제

def download(info: UpdateInfo, progress: Callable[[int, int], None] | None = None,
             transport=None, dest_dir: Path | None = None) -> Path:
    dest_dir = dest_dir or Path(tempfile.mkdtemp(prefix="catmoa_update_"))
    dest = dest_dir / info.asset_name
    try:
        with httpx.Client(follow_redirects=True, timeout=httpx.Timeout(600.0, connect=15.0), transport=transport,
                          headers={"User-Agent": f"catmoa/{__version__}"}) as c, c.stream("GET", info.asset_url) as r:
            if r.status_code >= 400:
                raise UpdateError(f"다운로드 실패 ({r.status_code})")
            total = int(r.headers.get("content-length") or info.asset_size or 0)
            done = 0
            with open(dest, "wb") as f:
                for chunk in r.iter_bytes(1024 * 256):
                    f.write(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total)
    except httpx.HTTPError as e:
        raise UpdateError(f"다운로드 중 오류: {e}") from e
    return dest


def extract(archive: Path) -> Path:
    """압축을 풀고 새 앱 루트(catmoa.app 또는 catmoa/)를 돌려준다."""
    out = archive.parent / "extracted"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir()
    if archive.name.endswith(".zip"):
        if platform.system() == "Darwin":
            # 심볼릭 링크·실행 권한 보존을 위해 ditto 사용
            subprocess.check_call(["ditto", "-x", "-k", str(archive), str(out)])
        else:
            with zipfile.ZipFile(archive) as z:
                z.extractall(out)
    else:
        with tarfile.open(archive, "r:gz") as t:
            t.extractall(out, filter="data")
    for cand in ("catmoa.app", "catmoa"):
        p = out / cand
        if p.exists():
            return p
    entries = [p for p in out.iterdir() if not p.name.startswith(".")]
    if len(entries) == 1:
        return entries[0]
    raise UpdateError("압축 파일 안에서 앱을 찾을 수 없습니다.")


# ---------------------------------------------------------------- 교체 스크립트

def make_swap_script(new_root: Path, target: Path, pid: int, script_dir: Path) -> tuple[list[str], Path]:
    """앱 종료 대기 → 기존 폴더 백업/삭제 → 새 폴더 이동 → 재실행. (명령, 스크립트 경로)"""
    sysname = platform.system()
    if sysname == "Windows":
        script = script_dir / "catmoa_update.cmd"
        exe = target / "catmoa.exe"
        script.write_text(
            "@echo off\r\n"
            f":wait\r\ntasklist /FI \"PID eq {pid}\" 2>NUL | find \"{pid}\" >NUL && (timeout /t 1 /nobreak >NUL & goto wait)\r\n"
            f"rmdir /s /q \"{target}.old\" 2>NUL\r\n"
            f"move \"{target}\" \"{target}.old\" >NUL\r\n"
            f"move \"{new_root}\" \"{target}\" >NUL\r\n"
            f"rmdir /s /q \"{target}.old\" 2>NUL\r\n"
            f"start \"\" \"{exe}\"\r\n"
            f"del \"%~f0\"\r\n",
            encoding="utf-8",
        )
        return ["cmd", "/c", str(script)], script

    script = script_dir / "catmoa_update.sh"
    if sysname == "Darwin":
        relaunch = f'xattr -cr "{target}" 2>/dev/null; open "{target}"'
    else:
        relaunch = f'chmod +x "{target}/catmoa"; nohup "{target}/catmoa" >/dev/null 2>&1 &'
    script.write_text(
        "#!/bin/sh\n"
        f"while kill -0 {pid} 2>/dev/null; do sleep 0.5; done\n"
        f'rm -rf "{target}.old"\n'
        f'mv "{target}" "{target}.old" && mv "{new_root}" "{target}" && rm -rf "{target}.old"\n'
        f"{relaunch}\n"
        f'rm -f "{script}"\n',
        encoding="utf-8",
    )
    script.chmod(0o755)
    return ["/bin/sh", str(script)], script


def apply(archive: Path, quit_app: Callable[[], None]) -> None:
    """압축 해제 → 교체 스크립트 실행 → 앱 종료. frozen 이 아니면 UpdateError."""
    if not is_frozen():
        raise UpdateError("소스로 실행 중이라 자동 설치를 할 수 없습니다. `git pull` 후 다시 실행하세요.")
    new_root = extract(archive)
    target = install_root()
    if not os.access(target.parent, os.W_OK):
        raise UpdateError(f"설치 폴더에 쓸 수 없습니다: {target.parent}\n수동으로 내려받아 교체하세요: {RELEASES_PAGE}")
    cmd, script = make_swap_script(new_root, target, os.getpid(), archive.parent)
    log.info("업데이트 스크립트 실행: %s", script)
    kwargs = {}
    if platform.system() == "Windows":
        kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kwargs)
    quit_app()
