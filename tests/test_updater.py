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
    assert name.startswith("catmoa-") and name.endswith((".zip", ".tar.gz"))
    if platform.system() == "Darwin":
        assert name == f"catmoa-macos-{'arm64' if platform.machine() == 'arm64' else 'x86_64'}.zip"


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
    with pytest.raises(updater.UpdateError, match="이 OS용 파일"):
        updater.check_latest(transport=tr)

    def boom(r):
        raise httpx.ConnectError("no net")
    with pytest.raises(updater.UpdateError, match="연결"):
        updater.check_latest(transport=httpx.MockTransport(boom))


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
