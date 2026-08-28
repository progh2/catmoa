import json
import os
import platform
import tarfile
import zipfile
from pathlib import Path

import httpx
import pytest

from src import __version__, updater


def test_version_compare():
    assert updater.parse_version("v1.2.3") == (1, 2, 3)
    assert updater.is_newer("1.2.0", "1.1.9") and not updater.is_newer("1.1.0", "1.1.0")
    assert updater.is_newer("v2.0", "1.9.9") and not updater.is_newer("", "1.0.0")


def test_asset_name_matches_build_naming():
    name = updater.asset_name_for_platform()
    assert name.startswith("catmoa-") and name.endswith((".dmg", ".exe", ".tar.gz"))
    if platform.system() == "Darwin":
        assert name == f"catmoa-macos-{'arm64' if platform.machine() == 'arm64' else 'x86_64'}.dmg"
    elif platform.system() == "Windows":
        assert name == "catmoa-windows-x86_64.exe"


def _release(tag, assets=None):
    want = updater.asset_name_for_platform()
    assets = assets if assets is not None else [want]
    return {"tag_name": tag, "body": "notes", "html_url": "https://x/rel",
            "assets": [{"name": a, "browser_download_url": f"https://x/{a}", "size": 10} for a in assets]}


def test_check_latest_newer_and_uptodate():
    newer = f"v{updater.parse_version(__version__)[0] + 1}.0.0"
    tr = httpx.MockTransport(lambda r: httpx.Response(200, json=_release(newer)))
    info = updater.check_latest(transport=tr)
    assert info and info.tag == newer and info.asset_name == updater.asset_name_for_platform()
    tr2 = httpx.MockTransport(lambda r: httpx.Response(200, json=_release(f"v{__version__}")))
    assert updater.check_latest(transport=tr2) is None
    tr3 = httpx.MockTransport(lambda r: httpx.Response(404, json={}))
    assert updater.check_latest(transport=tr3) is None


def test_check_latest_missing_asset_and_network_error():
    tr = httpx.MockTransport(lambda r: httpx.Response(200, json=_release("v99.0.0", assets=["other.zip"])))
    with pytest.raises(updater.UpdateError, match="용 파일이 아직 없습니다"):
        updater.check_latest(transport=tr)

    def boom(r):
        raise httpx.ConnectError("no net")
    with pytest.raises(updater.UpdateError, match="연결"):
        updater.check_latest(transport=httpx.MockTransport(boom))


def test_windows_arm_falls_back_to_x86_64(monkeypatch):
    monkeypatch.setattr(updater, "platform_key", lambda: ("windows", "arm64"))
    assert updater.asset_candidates() == ["catmoa-windows-arm64.exe", "catmoa-windows-x86_64.exe"]
    rel = {"tag_name": "v99.0.0", "body": "", "html_url": "https://x",
           "assets": [{"name": "catmoa-windows-x86_64.exe", "browser_download_url": "https://x/w.exe", "size": 5},
                      {"name": "catmoa-macos-arm64.dmg", "browser_download_url": "https://x/m.dmg", "size": 5}]}
    info = updater.check_latest(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=rel)))
    assert info and info.asset_name == "catmoa-windows-x86_64.exe"

    monkeypatch.setattr(updater, "platform_key", lambda: ("linux", "arm64"))
    assert updater.asset_candidates() == ["catmoa-linux-arm64.tar.gz"]     # 폴백 없음
    with pytest.raises(updater.UpdateError, match="linux/arm64"):
        updater.check_latest(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=rel)))


def test_download_with_progress(tmp_path):
    payload = b"x" * 1000
    tr = httpx.MockTransport(lambda r: httpx.Response(200, content=payload, headers={"content-length": "1000"}))
    info = updater.UpdateInfo("9.9.9", "v9.9.9", "", "", "catmoa-test.zip", "https://x/a.zip", 1000)
    seen = []
    p = updater.download(info, lambda d, t: seen.append((d, t)), transport=tr, dest_dir=tmp_path)
    assert p.read_bytes() == payload and seen[-1] == (1000, 1000)


def test_extract_zip_and_tar(tmp_path):
    # zip (catmoa/ 폴더)
    z = tmp_path / "a.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("catmoa/catmoa", "bin")
    if platform.system() != "Darwin":
        assert updater.extract(z).name == "catmoa"
    # tar.gz
    t = tmp_path / "b.tar.gz"
    src = tmp_path / "src" / "catmoa"; src.mkdir(parents=True); (src / "catmoa").write_text("bin")
    with tarfile.open(t, "w:gz") as tf:
        tf.add(src, arcname="catmoa")
    assert (updater.extract(t) / "catmoa").read_text() == "bin"


def test_extract_exe_returns_file_itself(tmp_path):
    exe = tmp_path / "catmoa-windows-x86_64.exe"; exe.write_bytes(b"MZ")
    assert updater.extract(exe) == exe


@pytest.mark.skipif(platform.system() != "Darwin", reason="hdiutil 은 macOS 전용")
def test_extract_dmg(tmp_path):
    import subprocess
    src = tmp_path / "stage" / "catmoa.app" / "Contents" / "MacOS"; src.mkdir(parents=True)
    (src / "catmoa").write_text("bin")
    dmg = tmp_path / "catmoa-macos-arm64.dmg"
    subprocess.check_call(["hdiutil", "create", "-volname", "catmoa", "-srcfolder", str(tmp_path / "stage"),
                           "-format", "UDZO", "-quiet", str(dmg)])
    app = updater.extract(dmg)
    assert app.name == "catmoa.app" and (app / "Contents" / "MacOS" / "catmoa").read_text() == "bin"
    assert not (tmp_path / "mnt").exists() or not any((tmp_path / "mnt").iterdir())  # 마운트 해제됨


def test_swap_script_single_exe(tmp_path, monkeypatch):
    monkeypatch.setattr(updater.platform, "system", lambda: "Windows")
    new = tmp_path / "dl" / "catmoa-windows-x86_64.exe"; new.parent.mkdir(); new.write_bytes(b"MZ")
    target = tmp_path / "Downloads" / "catmoa.exe"
    cmd, script = updater.make_swap_script(new, target, 777, tmp_path)
    text = script.read_text(encoding="utf-8")
    assert cmd[0] == "cmd" and "tasklist" in text and "777" in text
    assert f'move /y "{new}" "{target}"' in text and f'start "" "{target}"' in text
    assert "rmdir" not in text and f'del /f /q "{target}.old"' in text


def test_swap_script_windows_headless_safe(tmp_path, monkeypatch):
    """콘솔 없이 도는 스크립트: timeout 금지, ping 대기, 강제 종료·이동 재시도로 무한 대기 방지."""
    monkeypatch.setattr(updater.platform, "system", lambda: "Windows")
    new = tmp_path / "dl" / "catmoa-windows-x86_64.exe"; new.parent.mkdir(); new.write_bytes(b"MZ")
    target = tmp_path / "catmoa.exe"
    _, script = updater.make_swap_script(new, target, 4242, tmp_path)
    text = script.read_text(encoding="utf-8")
    assert "timeout" not in text and "ping -n 2 127.0.0.1" in text
    assert "taskkill /PID 4242 /F" in text and "GEQ 60" in text
    assert ":mv" in text and "GEQ 30" in text and ":fail" in text
    assert text.count(f'start "" "{target}"') == 2      # 성공/실패 경로 모두 재실행


def test_swap_script_generation(tmp_path):
    new_root = tmp_path / "new" / "catmoa"; new_root.mkdir(parents=True)
    target = tmp_path / "install" / "catmoa"; target.mkdir(parents=True)
    cmd, script = updater.make_swap_script(new_root, target, 12345, tmp_path)
    text = script.read_text(encoding="utf-8")
    assert "12345" in text and str(target) in text and str(new_root) in text
    if platform.system() == "Windows":
        assert cmd[0] == "cmd" and "tasklist" in text
    else:
        assert cmd[0] == "/bin/sh" and "kill -0 12345" in text
        assert os.access(script, os.X_OK)


def test_apply_refuses_when_not_frozen(tmp_path):
    with pytest.raises(updater.UpdateError, match="소스로 실행"):
        updater.apply(tmp_path / "x.zip", lambda: None)
