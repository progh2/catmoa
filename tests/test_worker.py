import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from src.pipeline.items import InputItem
from src.pipeline.worker import PipelineFailure, PipelineResult, PipelineWorker, parse_item
from src.parsers import ParseError
from tests.test_extract import FakeProvider


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _wait(app, cond, timeout=5.0):
    t0 = time.time()
    while not cond() and time.time() - t0 < timeout:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()
    return cond()


def test_parse_item_kinds(tmp_path):
    f = tmp_path / "a.txt"; f.write_text("hello", encoding="utf-8")
    assert parse_item(InputItem("file", f)).text == "hello"
    assert parse_item(InputItem("text", "memo")).text == "memo"
    assert parse_item(InputItem("coolm", "쪽지", source_label="쿨메신저: 김")).source == "쿨메신저: 김"
    with pytest.raises(ParseError):
        parse_item(InputItem("text", "   "))
    with pytest.raises(ParseError):
        parse_item(InputItem("image", b"garbage"))


def test_worker_sequential_and_errors(app):
    responses = [
        '{"items":[{"title":"a","date":"2026-09-01"}]}',
        '{"items":[{"title":"b","date":"2026-09-02"},{"title":"c","date":"2026-09-03"}]}',
        'not json', 'still bad',            # 3번째 항목: 재시도 후 실패
        '{"items":[]}',
    ]
    provider = FakeProvider(responses)
    w = PipelineWorker(lambda: provider)
    results, failures, phases, sizes, idles = [], [], [], [], []
    w.result.connect(results.append)
    w.failed.connect(failures.append)
    w.phase.connect(phases.append)
    w.queue_size.connect(sizes.append)
    w.idle.connect(lambda: idles.append(1))

    items = [InputItem("text", f"t{i}") for i in range(4)] + [InputItem("text", "   ")]
    w.enqueue(items)
    assert _wait(app, lambda: len(results) + len(failures) == 5)
    w.stop()

    assert [r.item.payload for r in results] == ["t0", "t1", "t3"]
    assert [len(r.extraction.items) for r in results] == [1, 2, 0]
    assert len(failures) == 2
    assert any("해석" in f.message for f in failures) and any("빈 텍스트" in f.message for f in failures)
    assert sizes[0] == 5 and sizes[-1] == 0
    assert phases[:2] == ["thinking", "eating"]
    assert idles == [1]
    assert not w.isRunning()
