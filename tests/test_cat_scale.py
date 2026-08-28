import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PIL import Image
from PySide6.QtWidgets import QApplication

from src import config as cfg
from src.ui import cat_faces
from src.ui.cat_widget import CatWidget


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _imgs(d):
    d.mkdir(parents=True, exist_ok=True)
    for n in ("idle", "eating"):
        Image.new("RGBA", (320, 320), (255, 200, 100, 255)).save(d / f"{n}.png")


def test_load_images_scale(app, tmp_path):
    _imgs(tmp_path)
    assert cat_faces.load_cat_images(tmp_path, scale=1.0).logical_size == (160, 160)
    assert cat_faces.load_cat_images(tmp_path, scale=0.5).logical_size == (80, 80)
    assert cat_faces.load_cat_images(tmp_path, scale=3.0).logical_size == (480, 480)
    assert cat_faces.load_cat_images(tmp_path, scale=9.0).logical_size == (480, 480)   # 상한 3.0


def test_widget_set_scale_image_mode(app, tmp_path, monkeypatch):
    monkeypatch.setenv("CATMOA_CONFIG_DIR", str(tmp_path / "cfg"))
    _imgs(tmp_path / "cfg" / "cat")
    c = cfg.Config(); c.ui.cat_scale = 2.0
    w = CatWidget(c); w.show(); app.processEvents()
    assert w.scale == 2.0 and w.face.width() == 320
    base_h_extra = w.height() - w.face.height()
    w.set_scale(0.5); app.processEvents()
    assert w.face.width() == 80 and w.width() == 80 and w.height() == 80 + base_h_extra
    w.set_update_available("9.9.9"); app.processEvents()
    assert w.update_badge.isVisible() and w.update_badge.x() < w.width()
    w.set_scale(1.0); app.processEvents()
    assert (w.width(), w.height()) == (160, 160 + base_h_extra)
    w.close(); w.deleteLater()


def test_widget_set_scale_text_mode(app, tmp_path, monkeypatch):
    monkeypatch.setenv("CATMOA_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setattr(cat_faces, "find_cat_dir", lambda: None)
    w = CatWidget(cfg.Config()); w.show(); app.processEvents()
    w0 = w.width()
    w.set_scale(2.0); app.processEvents()
    assert not w.image_mode and w.width() > w0 * 1.5
    w.set_scale(0.5); app.processEvents()
    assert w.width() < w0
    w.close(); w.deleteLater()


def test_settings_slider_roundtrip(app, tmp_path, monkeypatch):
    from src.ui.settings_dialog import SettingsDialog
    monkeypatch.setenv("CATMOA_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("CATMOA_NO_KEYRING", "1")
    dlg = SettingsDialog(cfg.Config())
    assert dlg.cat_scale.value() == 10 and dlg.cat_scale_label.text() == "1.0×"
    dlg.cat_scale.setValue(25)
    assert dlg.cat_scale_label.text() == "2.5×"
    dlg._save()
    assert cfg.Config.load().ui.cat_scale == 2.5
    assert dlg.cat_scale.minimum() == 5 and dlg.cat_scale.maximum() == 30


# ---------------------------------------------------------------- 슬라이더 실시간 반영 (#53)

def test_scale_slider_previews_live_and_restores_on_cancel(app, tmp_path, monkeypatch):
    monkeypatch.setenv("CATMOA_CONFIG_DIR", str(tmp_path))
    from src.ui.settings_dialog import SettingsDialog

    seen: list[float] = []
    c = cfg.Config()
    c.ui.cat_scale = 1.0
    dlg = SettingsDialog(c, scale_preview=seen.append)
    dlg._scale_timer.setInterval(0)

    dlg.cat_scale.setValue(22)
    assert dlg.cat_scale_label.text() == "2.2×"
    assert seen == []                      # 아직 디바운스 대기 (드래그 중 18장 재로딩 방지)
    dlg._apply_scale_preview()
    assert seen == [2.2]

    dlg.reject()                           # 취소 → 원래 크기로
    assert seen == [2.2, 1.0]


def test_scale_slider_keeps_value_on_save(app, tmp_path, monkeypatch):
    monkeypatch.setenv("CATMOA_CONFIG_DIR", str(tmp_path))
    from src.ui.settings_dialog import SettingsDialog

    seen: list[float] = []
    c = cfg.Config()
    dlg = SettingsDialog(c, scale_preview=seen.append)
    dlg.cat_scale.setValue(5)
    dlg._apply_scale_preview()
    dlg._save()
    assert c.ui.cat_scale == 0.5 and seen == [0.5]      # 저장 후에는 되돌리지 않는다


def test_scale_preview_survives_deleted_widget(app, tmp_path, monkeypatch):
    """고양이 위젯이 먼저 사라져도 설정 창이 죽지 않는다."""
    monkeypatch.setenv("CATMOA_CONFIG_DIR", str(tmp_path))
    from src.ui.settings_dialog import SettingsDialog

    def boom(_v):
        raise RuntimeError("Internal C++ object already deleted.")

    dlg = SettingsDialog(cfg.Config(), scale_preview=boom)
    dlg.cat_scale.setValue(15)
    dlg._apply_scale_preview()
    assert dlg._scale_preview is None
    dlg.reject()
