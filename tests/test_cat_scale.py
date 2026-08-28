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
