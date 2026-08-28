import os
import time
from datetime import datetime

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from src import config as cfg
from src.sources.coolm import CoolmError, CoolmReader, append_fake_message, create_fake_udb, parse_receive_date
from src.sources.coolm_watcher import CoolmWatcher, message_to_item

MSGS = [
    {"sender": "교무부장", "title": "회의 안내", "body": "내일 오후 3시 교무회의", "received": datetime(2026, 6, 8, 9, 0)},
    {"sender": "행정실", "title": "", "body": "6/12까지 출장비 청구서 제출", "received": datetime(2026, 6, 8, 10, 30)},
]


def test_parse_receive_date():
    assert parse_receive_date("2026/07/16 17:04:52 (목)") == datetime(2026, 7, 16, 17, 4, 52)


def test_reader_reads_copy_and_keeps_original(tmp_path):
    path = create_fake_udb(tmp_path / "Memo", MSGS)
    mtime = os.path.getmtime(path)
    with CoolmReader(str(tmp_path / "Memo")) as r:
        assert r.latest_key() == 2
        msgs = r.messages_after(0)
        assert [m.sender for m in msgs] == ["교무부장", "행정실"]
        assert msgs[0].received == datetime(2026, 6, 8, 9, 0) and msgs[0].is_unread
        assert "제목: 회의 안내" in msgs[0].text and "내일 오후 3시" in msgs[0].text
        assert r.messages_after(1)[0].key == 2
        assert [m.key for m in r.latest_messages(1)] == [2]
    assert os.path.getmtime(path) == mtime


def test_reader_errors(tmp_path):
    with pytest.raises(CoolmError):
        CoolmReader(str(tmp_path / "nope")).__enter__()
    (tmp_path / "empty").mkdir()
    with pytest.raises(CoolmError):
        CoolmReader(str(tmp_path / "empty")).__enter__()
    import sqlite3
    bad = tmp_path / "bad"; bad.mkdir()
    con = sqlite3.connect(bad / "x.udb"); con.execute("CREATE TABLE other (a)"); con.commit(); con.close()
    with pytest.raises(CoolmError, match="tbl_recv"):
        CoolmReader(str(bad)).__enter__()


def test_message_to_item(tmp_path):
    create_fake_udb(tmp_path, MSGS)
    with CoolmReader(str(tmp_path)) as r:
        it = message_to_item(r.messages_after(0)[0])
    assert it.kind == "coolm" and it.reference_date.isoformat() == "2026-06-08"
    assert it.source_label.startswith("쿨메신저: 교무부장") and it.origin_ref == "1"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _pump(app, secs):
    t0 = time.time()
    while time.time() - t0 < secs:
        app.processEvents()
        time.sleep(0.02)


def test_watcher_skips_existing_then_picks_new(app, tmp_path, monkeypatch):
    monkeypatch.setenv("CATMOA_CONFIG_DIR", str(tmp_path / "cfg"))
    memo = tmp_path / "Memo"
    path = create_fake_udb(memo, MSGS)
    c = cfg.Config()
    c.coolm.enabled = True
    c.coolm.poll_seconds = 5
    c.coolm.memo_dir = str(memo)
    w = CoolmWatcher(c)
    got, errs = [], []
    w.new_items.connect(got.append)
    w.error.connect(errs.append)
    w.apply_config()
    assert w.active
    _pump(app, 0.8)                       # 첫 폴링: 기존 쪽지 건너뜀
    assert got == [] and c.coolm.last_message_key == 2
    assert cfg.Config.load().coolm.last_message_key == 2   # 저장됨

    append_fake_message(path, {"sender": "학생부", "body": "다음 주 월요일 학폭위", "received": datetime(2026, 6, 9, 8)})
    w.poll()
    assert len(got) == 1 and got[0][0].payload.endswith("학폭위") and c.coolm.last_message_key == 3
    w.poll()                              # 중복 없음
    assert len(got) == 1 and errs == []

    c.coolm.enabled = False
    w.apply_config()
    assert not w.active
    w.deleteLater()


def test_watcher_error_once(app, tmp_path, monkeypatch):
    monkeypatch.setenv("CATMOA_CONFIG_DIR", str(tmp_path / "cfg"))
    c = cfg.Config()
    c.coolm.enabled = True
    c.coolm.memo_dir = str(tmp_path / "missing")
    w = CoolmWatcher(c)
    errs = []
    w.error.connect(errs.append)
    w.poll(); w.poll()
    assert len(errs) == 1 and "폴더가 없습니다" in errs[0]
    w.deleteLater()
