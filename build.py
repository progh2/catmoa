"""PyInstaller 빌드 스크립트 (3-OS 공용).

1. 환경변수 CATMOA_GOOGLE_CLIENT_ID / CATMOA_GOOGLE_CLIENT_SECRET (또는 .env) → src/_secrets.py 생성
2. 아이콘 생성
3. pyinstaller catmoa.spec
4. dist/ 산출물을 OS별 배포 파일로 만든다:
   macOS → catmoa-macos-{arch}.dmg, Windows → catmoa-windows-{arch}.exe(단일 실행 파일), Linux → catmoa-linux-{arch}.tar.gz

사용: python build.py [--no-archive]
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def write_secrets() -> None:
    from src.config import google_client

    cid, csec = google_client()
    p = ROOT / "src" / "_secrets.py"
    p.write_text(
        '"""빌드 시 생성됨 — git 에 올리지 말 것."""\n'
        f"GOOGLE_CLIENT_ID = {cid!r}\nGOOGLE_CLIENT_SECRET = {csec!r}\n",
        encoding="utf-8",
    )
    print("secrets:", "client id 포함" if cid else "⚠ client id 없음 (Google 로그인 불가 빌드)")


def make_icon() -> None:
    subprocess.check_call([sys.executable, str(ROOT / "tools" / "make_icon.py")])


def run_pyinstaller() -> None:
    for d in ("build", "dist"):
        shutil.rmtree(ROOT / d, ignore_errors=True)
    subprocess.check_call([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", str(ROOT / "catmoa.spec")], cwd=ROOT)


def make_dmg(app: Path, out: Path) -> None:
    """catmoa.app + /Applications 바로가기를 담은 압축 dmg (더블클릭 → 드래그 설치)."""
    staging = out.parent / "dmg_staging"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir()
    subprocess.check_call(["ditto", str(app), str(staging / app.name)])
    (staging / "Applications").symlink_to("/Applications")
    out.unlink(missing_ok=True)
    subprocess.check_call(["hdiutil", "create", "-volname", "catmoa", "-srcfolder", str(staging),
                           "-ov", "-format", "UDZO", "-quiet", str(out)])
    shutil.rmtree(staging, ignore_errors=True)


def archive() -> Path:
    sysname = platform.system()
    arch = platform.machine().lower()
    arch = {"amd64": "x86_64", "x86_64": "x86_64", "arm64": "arm64", "aarch64": "arm64"}.get(arch, arch)
    dist = ROOT / "dist"
    if sysname == "Darwin":
        out = dist / f"catmoa-macos-{arch}.dmg"
        make_dmg(dist / "catmoa.app", out)
    elif sysname == "Windows":
        # onefile 빌드 → dist/catmoa.exe 하나. 이름만 배포용으로 바꾼다
        out = dist / f"catmoa-windows-{arch}.exe"
        shutil.copy2(dist / "catmoa.exe", out)
    else:
        out = dist / f"catmoa-linux-{arch}.tar.gz"
        shutil.make_archive(str(out).replace(".tar.gz", ""), "gztar", root_dir=dist, base_dir="catmoa")
    print("archive:", out, f"{out.stat().st_size / 1e6:.1f} MB")
    return out


def main() -> None:
    os.chdir(ROOT)
    write_secrets()
    make_icon()
    run_pyinstaller()
    if "--no-archive" not in sys.argv:
        archive()


if __name__ == "__main__":
    main()
