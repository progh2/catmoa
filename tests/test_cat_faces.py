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


def _png(path, size=(256, 256), color=(255, 200, 100, 255)):
    Image.new("RGBA", size, color).save(path)


def _make_set(d):
    d.mkdir(parents=True, exist_ok=True)
    _png(d / "idle.png")
    _png(d / "eating_1.png"); _png(d / "eating_2.png"); _png(d / "eating_10.png")
    _png(d / "Hover.png")                      # 대소문자 무시
    _png(d / "ignored.png")                    # 알 수 없는 이름은 무시


def test_load_images_frames_and_fallback(app, tmp_path):
    _make_set(tmp_path / "cat")
    s = cat_faces.load_cat_images(tmp_path / "cat")
    assert s is not None and s.logical_size == (128, 128)
    assert len(s.frames["idle"]) == 1 and len(s.frames["eating"]) == 3 and "hover" in s.frames
    assert s.frames_for("happy") is s.frames["idle"]          # 없는 상태 → idle
    assert s.frames["idle"][0].devicePixelRatio() == 2.0


def test_load_images_requires_idle_and_scales_large(app, tmp_path):
    d = tmp_path / "noidle"; d.mkdir(); _png(d / "eating.png")
    assert cat_faces.load_cat_images(d) is None
    big = tmp_path / "big"; big.mkdir(); _png(big / "idle.png", size=(1200, 600))
    s = cat_faces.load_cat_images(big)
    assert s.logical_size == (220, 110)


def test_find_cat_dir_prefers_user_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CATMOA_CONFIG_DIR", str(tmp_path / "cfg"))
    assert cat_faces.find_cat_dir() in (None, cat_faces.bundled_assets_dir())
    user = tmp_path / "cfg" / "cat"
    user.mkdir(parents=True)
    _png(user / "idle.png")
    assert cat_faces.find_cat_dir() == user


def test_widget_image_mode(app, tmp_path, monkeypatch):
    monkeypatch.setenv("CATMOA_CONFIG_DIR", str(tmp_path / "cfg"))
    _make_set(tmp_path / "cfg" / "cat")
    w = CatWidget(cfg.Config())
    assert w.image_mode and w.face.property("mode") == "image"
    w.show(); app.processEvents()
    base = (w.width(), w.height())
    assert w.face.width() == 128 and w.face.height() == 128 and base[1] > 128
    w._enter("eating"); w._tick(); app.processEvents()
    assert w.face.pixmap() is not None and (w.width(), w.height()) == base
    w._enter("sleeping"); app.processEvents()               # 없는 상태 → idle 이미지, 크기 불변
    assert (w.width(), w.height()) == base
    w.close(); w.deleteLater()


def test_widget_text_mode_without_images(app, tmp_path, monkeypatch):
    monkeypatch.setenv("CATMOA_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setattr(cat_faces, "bundled_assets_dir", lambda: tmp_path / "none")
    w = CatWidget(cfg.Config())
    assert not w.image_mode and "ω" in w.face.text()
    w.close(); w.deleteLater()
