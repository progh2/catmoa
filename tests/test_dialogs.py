import os
from datetime import datetime

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from src import config as cfg
from src.extract.schema import ScheduleItem
from src.ui.review_dialog import ReviewDialog
from src.ui.settings_dialog import SettingsDialog


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("CATMOA_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("CATMOA_NO_KEYRING", "1")


def _items():
    return [
        ScheduleItem(title="운영위원회", start=datetime(2026, 9, 3, 14), end=datetime(2026, 9, 3, 16), kind="event", location="회의실"),
        ScheduleItem(title="신청서 제출", start=datetime(2026, 9, 10), all_day=True, kind="task", confidence=0.7),
    ]


def test_review_defaults_and_bulk(app):
    s = cfg.ScheduleSettings(alarm_enabled=True, alarm_minutes=15)
    d = ReviewDialog(_items(), s, source_label="공문.hwp", warnings=["경고"])
    ds = d.decisions()
    assert [x.target for x in ds] == ["calendar", "task"]
    assert all(x.alarm_minutes == 15 for x in ds)
    assert ds[0].item.end == datetime(2026, 9, 3, 16) and ds[1].item.all_day

    d._bulk_target("task")
    assert [x.target for x in d.decisions()] == ["task", "task"]
    d._bulk_check(False)
    assert d.decisions() == []
    d._bulk_check(True)
    assert len(d.decisions()) == 2


def test_review_edit_and_uncheck(app):
    s = cfg.ScheduleSettings(alarm_enabled=False, default_target="calendar")
    d = ReviewDialog(_items(), s)
    r0, r1 = d.rows
    assert r1.target.currentData() == "calendar"      # 강제 기본 대상
    r0.title.setText("  수정된 제목 ")
    r0.alarm.setChecked(True)
    r0.alarm_min.setValue(5)
    r0.all_day.setChecked(True)
    r1.check.setChecked(False)
    got = []
    d.submitted.connect(got.append)
    d._submit()
    assert len(got[0]) == 1
    dec = got[0][0]
    assert dec.item.title == "수정된 제목" and dec.alarm_minutes == 5 and dec.item.all_day
    assert dec.item.start == datetime(2026, 9, 3) and dec.item.alarm_minutes == 5


def test_settings_save_roundtrip(app):
    c = cfg.Config()
    dlg = SettingsDialog(c)
    dlg.provider.setCurrentIndex(list(dlg.provider.itemData(i) for i in range(dlg.provider.count())).index("claude"))
    dlg.api_key.setText("sk-test")
    dlg.model.setEditText("claude-opus-5")
    dlg.alarm_minutes.setValue(45)
    dlg.default_target.setCurrentIndex(2)
    dlg.inbox_name.setText("받은편지함")
    dlg.coolm_enabled.setChecked(True)
    dlg.coolm_poll.setValue(60)
    dlg.coolm_dir.setText("/tmp/memo")
    saved = []
    dlg.saved.connect(saved.append)
    dlg._save()
    assert saved
    c2 = cfg.Config.load()
    assert c2.llm.provider == "claude" and c2.llm.model == "claude-opus-5"
    assert cfg.get_secret(cfg.SECRET_CLAUDE_API_KEY) == "sk-test"
    assert c2.schedule.alarm_minutes == 45 and c2.schedule.default_target == "task"
    assert c2.schedule.inbox_list_name == "받은편지함"
    assert c2.coolm.enabled and c2.coolm.poll_seconds == 60 and c2.coolm.memo_dir == "/tmp/memo"


def test_settings_google_disabled_without_auth(app):
    dlg = SettingsDialog(cfg.Config())
    assert not dlg.btn_login.isEnabled() and "v0.3" in dlg.google_status.text()
