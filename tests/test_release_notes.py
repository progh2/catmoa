"""릴리스 노트 생성/표시 (#62)."""
import os
import subprocess
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import release_notes as rn


def test_clean_strips_type_issue_refs_and_version():
    assert rn.clean("feat: 고양이 크기 10배 (closes #61)") == ("feat", "고양이 크기 10배 (#61)")
    assert rn.clean("fix: 울상 문제 수정 (closes #52)") == ("fix", "울상 문제 수정 (#52)")
    assert rn.clean("chore: A 상향 (closes #57) + B (closes #58, closes #59)")[1] == "A 상향 + B (#57, #58, #59)"
    assert rn.clean("feat: 마스킹 추가, 버전 1.4.13 (closes #60)")[1] == "마스킹 추가 (#60)"
    assert rn.clean("설명만 있는 커밋") == ("chore", "설명만 있는 커밋")


def test_render_groups_by_type_and_keeps_order():
    groups = {"🐛 고친 것": ["나중 항목"], "✨ 새로워진 점": ["먼저 항목"]}
    out = rn.render("v1.2.3", "v1.2.2", groups, "progh2/catmoa")
    assert out.startswith("# catmoa 1.2.3")
    assert out.index("✨ 새로워진 점") < out.index("🐛 고친 것")      # 새 기능이 먼저
    assert "- 먼저 항목" in out and "- 나중 항목" in out
    assert "## 내려받기" in out and "compare/v1.2.2...v1.2.3" in out


def test_render_without_changes_or_previous_tag():
    out = rn.render("v0.1.0", None, {}, "progh2/catmoa")
    assert "작은 수정만 있었습니다." in out and "compare/" not in out


def test_real_repo_tag_produces_korean_notes():
    """실제 저장소에서 돌려 본다 (태그가 없는 체크아웃이면 건너뜀)."""
    try:
        tags = rn.run("tag", "--list", "v*", "--sort=-v:refname").splitlines()
    except subprocess.CalledProcessError:  # pragma: no cover
        pytest.skip("git 저장소가 아님")
    if len(tags) < 2:  # pragma: no cover
        pytest.skip("태그가 부족")
    out = rn.render(tags[0], tags[1], rn.collect(tags[0], tags[1]), "progh2/catmoa")
    assert out.startswith(f"# catmoa {tags[0].lstrip('v')}")
    assert "catmoa-windows-x86_64.exe" in out       # 내려받기 안내 포함
    assert len(out.splitlines()) > 10


def test_settings_trims_notes_for_in_app_view():
    from src.ui.settings_dialog import SettingsDialog

    notes = ("# catmoa 1.4.13\n\n## ✨ 새로워진 점\n- 무언가 (#60)\n\n"
             "## 내려받기\n\n| 표 | 표 |\n|---|---|\n\n**Full Changelog**: https://x/y")
    t = SettingsDialog.trim_notes(notes)
    assert t.startswith("## ✨ 새로워진 점") and "- 무언가 (#60)" in t
    assert "내려받기" not in t and "Full Changelog" not in t
    assert SettingsDialog.trim_notes("**Full Changelog**: https://x/y") == ""
    assert SettingsDialog.trim_notes("") == ""


def test_update_tab_shows_notes_and_falls_back(app_qt, tmp_path, monkeypatch):
    from src import config as cfg
    from src.ui.settings_dialog import SettingsDialog
    from src.updater import UpdateInfo

    monkeypatch.setenv("CATMOA_CONFIG_DIR", str(tmp_path))
    full = UpdateInfo(version="9.9.9", tag="v9.9.9", asset_name="x.dmg", asset_url="https://x/y",
                      html_url="https://x/rel", notes="# catmoa 9.9.9\n\n## ✨ 새로워진 점\n- 큰 변화 (#1)\n\n## 내려받기\n표")
    dlg = SettingsDialog(cfg.Config(), initial_tab="update", update_info=full)
    shown = dlg.update_notes.toPlainText()
    assert "새로워진 점" in shown and "큰 변화" in shown and "내려받기" not in shown

    empty = UpdateInfo(version="9.9.9", tag="v9.9.9", asset_name="x.dmg", asset_url="https://x/y",
                       html_url="https://x/rel", notes="**Full Changelog**: https://x/y")
    dlg2 = SettingsDialog(cfg.Config(), initial_tab="update", update_info=empty)
    assert "변경 내역이 없습니다" in dlg2.update_notes.toPlainText()


@pytest.fixture(scope="module")
def app_qt():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])
