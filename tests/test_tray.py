import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from src.ui.tray import CatTray, tray_icons


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_tray_icons_exist(app):
    normal, sleeping = tray_icons()
    assert not normal.isNull() and not sleeping.isNull()


def test_tray_toggle_and_icons(app):
    t = CatTray()
    got = []
    t.toggle_requested.connect(lambda: got.append(1))
    assert not t.hidden and t.act_toggle.text() == "고양이 숨기기"
    normal_key = t.icon().cacheKey()
    t.set_hidden(True)
    assert t.hidden and t.act_toggle.text() == "고양이 보이기" and "자고" in t.toolTip()
    assert t.icon().cacheKey() != normal_key           # 잠자는 아이콘으로 교체
    t.set_hidden(False)
    assert t.icon().cacheKey() == normal_key
    t._on_activated(QSystemTrayIcon.ActivationReason.Trigger)
    t._on_activated(QSystemTrayIcon.ActivationReason.Context)   # 우클릭은 토글 아님
    assert got == [1]
    t.act_toggle.trigger()
    assert got == [1, 1]


def test_cat_widget_has_hide_signal(app, tmp_path, monkeypatch):
    from src import config as cfg
    from src.ui import cat_faces
    from src.ui.cat_widget import CatWidget
    monkeypatch.setenv("CATMOA_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(cat_faces, "find_cat_dir", lambda: None)
    w = CatWidget(cfg.Config())
    got = []
    w.hide_requested.connect(lambda: got.append(1))
    w.hide_requested.emit()
    assert got == [1]
    w.close(); w.deleteLater()
