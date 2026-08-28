"""고양이 위젯 — 오프스크린 QApplication 으로 입력 정규화·상태 전이 검증."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QMimeData, QUrl
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from src import config as cfg
from src.ui.cat_widget import CatWidget


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def widget(app, tmp_path, monkeypatch):
    monkeypatch.setenv("CATMOA_CONFIG_DIR", str(tmp_path))
    w = CatWidget(cfg.Config())
    yield w
    w.close()


def test_initial_state(widget):
    assert widget.state == "idle"
    assert "ω" in widget.face.text()


def test_file_urls(widget, tmp_path):
    ok = tmp_path / "a.hwp"; ok.write_bytes(b"x")
    bad = tmp_path / "b.docx"; bad.write_bytes(b"x")
    sub = tmp_path / "dir"; sub.mkdir(); (sub / "c.pdf").write_bytes(b"x"); (sub / "d.exe").write_bytes(b"x")
    md = QMimeData()
    md.setUrls([QUrl.fromLocalFile(str(ok)), QUrl.fromLocalFile(str(bad)), QUrl.fromLocalFile(str(sub))])
    msgs = []
    widget.unsupported.connect(msgs.append)
    items = widget.items_from_mime(md)
    assert [(i.kind, i.payload.name) for i in items] == [("file", "a.hwp"), ("file", "c.pdf")]
    assert msgs and "b.docx" in msgs[0]


def test_image(widget):
    img = QImage(10, 10, QImage.Format.Format_RGB32)
    img.fill(QColor("white"))
    md = QMimeData()
    md.setImageData(img)
    items = widget.items_from_mime(md, source="클립보드")
    assert len(items) == 1 and items[0].kind == "image"
    assert items[0].payload.startswith(b"\x89PNG") and "클립보드" in items[0].source_label


def test_text_and_path_text(widget, tmp_path):
    md = QMimeData()
    md.setText("  내일 3시 회의\n장소: 회의실 ")
    items = widget.items_from_mime(md)
    assert items[0].kind == "text" and items[0].payload.startswith("내일 3시")
    f = tmp_path / "x.pdf"; f.write_bytes(b"x")
    md2 = QMimeData(); md2.setText(str(f))
    assert widget.items_from_mime(md2)[0].kind == "file"


def test_empty_mime(widget):
    assert widget.items_from_mime(QMimeData()) == []


def test_state_transitions(widget):
    widget.set_busy(True, "thinking")
    assert widget.state == "thinking"
    widget.set_phase("eating")
    assert widget.state == "eating" and "🍙" in widget.face.text() or "🍚" in widget.face.text()
    widget.set_busy(False)
    assert widget.state == "happy"
    widget.show_error("boom")
    assert widget.state == "error" and widget.face.toolTip() == "boom"
    widget.set_queue_size(3)
    assert widget.badge.text() == "3" and not widget.badge.isHidden()
    widget.set_queue_size(0)
    assert widget.badge.isHidden()


def test_deliver_emits(widget):
    got = []
    widget.items_received.connect(got.append)
    md = QMimeData(); md.setText("hi")
    widget._deliver(widget.items_from_mime(md))
    assert got and got[0][0].payload == "hi" and widget.state == "thinking"
