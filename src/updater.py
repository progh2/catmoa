"""자동 업데이트.

1. GitHub Releases `latest` 조회 → 현재 버전보다 새로우면 UpdateInfo
2. OS/아키텍처에 맞는 산출물 다운로드 (진행률 콜백)
   macOS → .dmg (catmoa.app), Windows → 단일 .exe, Linux → .tar.gz (catmoa/ 폴더)
3. 새 앱을 꺼낸 뒤(dmg 마운트·복사 / tar 해제 / exe 는 그대로), 앱 종료를 기다렸다가
   설치 대상(.app 번들 / exe 파일 / 폴더)을 교체하고 재실행하는 스크립트를 띄운다
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
    ext = {"macos": "dmg", "windows": "exe"}.get(name, "tar.gz")
    return f"catmoa-{name}-{arch}.{ext}"


def asset_candidates() -> list[str]:
    """우선순위대로 찾을 산출물 이름. 정확한 아키텍처가 없으면 에뮬레이션으로 돌릴 수 있는 것으로 폴백.

    - Windows on ARM (Parallels 등): x64 에뮬레이션이 있으므로 x86_64 exe 로 폴백
    - Linux aarch64: x86_64 는 못 돌리므로 폴백 없음
    """
    name, arch = platform_key()
    ext = {"macos": "dmg", "windows": "exe"}.get(name, "tar.gz")
    cands = [f"catmoa-{name}-{arch}.{ext}"]
    if name == "windows" and arch != "x86_64":
        cands.append(f"catmoa-windows-x86_64.{ext}")
    return cands


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def install_root() -> Path:
    """교체 대상: macOS 는 .app 번들, Windows 는 단일 exe 파일, Linux 는 onedir 폴더."""
    exe = Path(sys.executable).resolve()
    sysname = platform.system()
    if sysname == "Darwin":
        for p in exe.parents:
            if p.suffix == ".app":
                return p
    elif sysname == "Windows":
        return exe
    return exe.parent


# ---------------------------------------------------------------- 조회

def _check_latest_fallback(c: httpx.Client) -> UpdateInfo | None:
    """API 한도(403/429) 등으로 API 를 못 쓸 때: github.com/…/releases/latest 의 리다이렉트로 최신 태그를 알아내고
    다운로드 URL 을 직접 구성한다 (한도 없음). 릴리스 노트는 없다."""
    r = c.get(f"https://github.com/{REPO}/releases/latest", follow_redirects=False)
    loc = r.headers.get("location", "")
    if r.status_code not in (301, 302, 303, 307, 308) or "/releases/tag/" not in loc:
        if r.status_code == 404:
            return None
        raise UpdateError(f"업데이트 확인 실패 (github.com {r.status_code})")
    tag = loc.rsplit("/releases/tag/", 1)[1].strip("/")
    version = tag.lstrip("vV")
    if not is_newer(version):
        return None
    for name in asset_candidates():
        url = f"https://github.com/{REPO}/releases/download/{tag}/{name}"
        h = c.head(url, follow_redirects=False)
        if h.status_code in (200, 302, 303, 307):
            return UpdateInfo(version=version, tag=tag, notes="", html_url=loc, asset_name=name, asset_url=url)
    pk = platform_key()
    raise UpdateError(f"새 버전 {tag} 이 있지만 이 환경({pk[0]}/{pk[1]})용 파일이 아직 없습니다. {RELEASES_PAGE}")


def check_latest(transport=None, timeout: float = 10.0) -> UpdateInfo | None:
    """새 버전이 있으면 UpdateInfo, 최신이면 None. 네트워크 오류는 UpdateError.
    GitHub API 가 한도 초과(403/429) 등으로 실패하면 리다이렉트 기반 폴백을 쓴다."""
    try:
        with httpx.Client(timeout=timeout, transport=transport, follow_redirects=True,
                          headers={"Accept": "application/vnd.github+json", "User-Agent": f"catmoa/{__version__}"}) as c:
            r = c.get(LATEST_URL)
            if r.status_code == 404:
                return None
            if r.status_code >= 400:
                log.info("GitHub API %s → 리다이렉트 폴백", r.status_code)
                return _check_latest_fallback(c)
            data = r.json()
            return _info_from_api(data)
    except httpx.HTTPError as e:
        raise UpdateError(f"업데이트 서버에 연결할 수 없습니다: {e}") from e


def _info_from_api(data: dict) -> UpdateInfo | None:
    tag = data.get("tag_name", "")
    version = tag.lstrip("vV")
    if not is_newer(version):
        return None
    assets = {a.get("name"): a for a in data.get("assets", [])}
    asset = next((assets[c] for c in asset_candidates() if c in assets), None)
    if asset is None:
        name, arch = platform_key()
        raise UpdateError(f"새 버전 {tag} 이 있지만 이 환경({name}/{arch})용 파일이 아직 없습니다. "
                          f"릴리스 페이지에서 직접 내려받으세요: {RELEASES_PAGE}")
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


def _extract_dmg(dmg: Path, out: Path) -> None:
    mnt = out.parent / "mnt"
    mnt.mkdir(exist_ok=True)
    subprocess.check_call(["hdiutil", "attach", "-nobrowse", "-readonly", "-quiet",
                           "-mountpoint", str(mnt), str(dmg)])
    try:
        app = next((p for p in mnt.iterdir() if p.suffix == ".app"), None)
        if app is None:
            raise UpdateError("dmg 안에서 앱을 찾을 수 없습니다.")
        subprocess.check_call(["ditto", str(app), str(out / app.name)])
    finally:
        subprocess.call(["hdiutil", "detach", "-quiet", "-force", str(mnt)])


def extract(archive: Path) -> Path:
    """다운로드한 파일에서 새 앱(catmoa.app / catmoa/ 폴더 / catmoa.exe)을 꺼내 그 경로를 돌려준다."""
    if archive.name.endswith(".exe"):
        return archive  # 단일 실행 파일: 그대로 교체
    out = archive.parent / "extracted"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir()
    if archive.name.endswith(".dmg"):
        _extract_dmg(archive, out)
    elif archive.name.endswith(".zip"):
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
    """앱 종료 대기 → 기존 항목 백업/삭제 → 새 항목 이동 → 재실행. (명령, 스크립트 경로)

    target 이 파일(단일 exe)이면 파일 교체, 폴더(.app / onedir)면 폴더 교체.
    """
    sysname = platform.system()
    if sysname == "Windows":
        script = script_dir / "catmoa_update.cmd"
        old = f"{target}.old"
        if target.suffix.lower() == ".exe" or new_root.suffix.lower() == ".exe":
            exe = target
            clean = f'del /f /q "{old}" 2>NUL'
            move_new = f'move /y "{new_root}" "{target}" >NUL'
        else:
            exe = target / "catmoa.exe"
            clean = f'rmdir /s /q "{old}" 2>NUL'
            move_new = f'move "{new_root}" "{target}" >NUL'
        # 주의: 이 스크립트는 콘솔 없이(CREATE_NO_WINDOW) 돌므로 `timeout` 은 쓸 수 없다(stdin 필요) → ping 으로 대기.
        # 앱이 60초 안에 안 죽으면 강제 종료, 파일 잠금이 풀릴 때까지 move 를 재시도해 무한 대기를 막는다.
        script.write_text(
            "@echo off\r\n"
            "setlocal\r\n"
            "set /a n=0\r\n"
            ":wait\r\n"
            f'tasklist /FI "PID eq {pid}" /NH 2>NUL | find "{pid}" >NUL || goto swap\r\n'
            "set /a n+=1\r\n"
            f"if %n% GEQ 60 taskkill /PID {pid} /F >NUL 2>&1\r\n"
            "ping -n 2 127.0.0.1 >NUL\r\n"
            "goto wait\r\n"
            ":swap\r\n"
            "ping -n 2 127.0.0.1 >NUL\r\n"
            f"{clean}\r\n"
            "set /a m=0\r\n"
            ":mv\r\n"
            f'move /y "{target}" "{old}" >NUL 2>&1 && goto mv2\r\n'
            "set /a m+=1\r\n"
            "if %m% GEQ 30 goto fail\r\n"
            "ping -n 2 127.0.0.1 >NUL\r\n"
            "goto mv\r\n"
            ":mv2\r\n"
            f"{move_new}\r\n"
            f"{clean}\r\n"
            f'start "" "{exe}"\r\n'
            'del "%~f0"\r\n'
            "exit /b 0\r\n"
            ":fail\r\n"
            f'start "" "{exe}"\r\n'
            'del "%~f0"\r\n'
            "exit /b 1\r\n",
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
    """새 앱 꺼내기 → 교체 스크립트 실행 → 앱 종료. frozen 이 아니면 UpdateError."""
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
        # CREATE_NO_WINDOW: 숨김 콘솔을 만들어 cmd 와 자식(tasklist/find/ping)이 공유 →
        # DETACHED_PROCESS 를 쓰면 콘솔이 없어서 자식 명령마다 검은 창이 뜬다.
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        kwargs["close_fds"] = True
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kwargs)
    quit_app()
