import os
from datetime import datetime

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from src import config as cfg
from src.extract.schema import ScheduleItem
from src.ui.review_dialog import ReviewDialog, default_targets
from src.ui.settings_dialog import SettingsDialog

LISTS = [("L1", "내 할 일"), ("L2", "학교"), ("L3", "담임")]


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
        ScheduleItem(title="신청서 제출", start=datetime(2026, 9, 10), all_day=True, kind="task", confidence=0.7, category="학교"),
    ]


def test_default_targets():
    ev, tk = _items()
    assert default_targets(ev, cfg.ScheduleSettings()) == {"calendar"}
    assert default_targets(tk, cfg.ScheduleSettings()) == {"task"}
    assert default_targets(ev, cfg.ScheduleSettings(default_target="both")) == {"calendar", "task"}
    assert default_targets(ev, cfg.ScheduleSettings(default_target="task")) == {"task"}


def test_review_defaults_bulk_and_category(app):
    s = cfg.ScheduleSettings(alarm_enabled=True, alarm_minutes=15)
    d = ReviewDialog(_items(), s, source_label="공문.hwp", warnings=["경고"], tasklists=LISTS)
    ds = d.decisions()
    assert [x.targets for x in ds] == [{"calendar"}, {"task"}]
    assert all(x.alarm_minutes == 15 for x in ds)
    assert ds[1].tasklist_id == "L2" and ds[1].tasklist_name == "학교"      # category → 목록 자동 선택
    assert ds[0].tasklist_id == "" and ds[0].item.end == datetime(2026, 9, 3, 16)

    d._bulk_targets({"calendar", "task"})
    assert all(x.targets == {"calendar", "task"} for x in d.decisions())
    d._bulk_targets({"task"})
    assert all(x.targets == {"task"} for x in d.decisions())
    d._bulk_check(False)
    assert d.decisions() == []
    d._bulk_check(True)
    assert len(d.decisions()) == 2


def test_review_no_target_excluded_and_kind_follows_targets(app):
    d = ReviewDialog(_items(), cfg.ScheduleSettings(), tasklists=LISTS)
    r0, r1 = d.rows
    r0.cal.setChecked(False)                       # 아무 대상도 없음 → 제외
    assert len(d.decisions()) == 1
    r1.set_targets({"calendar"})                   # task 항목을 캘린더만 → kind event
    assert d.decisions()[0].item.kind == "event"
    r1.set_targets({"calendar", "task"})           # 둘 다 → 원래 kind 유지
    assert d.decisions()[0].item.kind == "task" and d.decisions()[0].target == "both"


def test_review_edit_and_submit(app):
    s = cfg.ScheduleSettings(alarm_enabled=False, default_target="calendar", tasklist_id="L3")
    d = ReviewDialog(_items(), s, tasklists=LISTS)
    r0, r1 = d.rows
    assert r1.targets() == {"calendar"} and not r1.tasklist.isEnabled()
    r1.task.setChecked(True)
    assert r1.tasklist.isEnabled() and r1.tasklist.currentData() == "L2"   # category 우선
    r0.title.setText("  수정된 제목 ")
    r0.alarm.setChecked(True)
    r0.alarm_min.setValue(5)
    r0.all_day.setChecked(True)
    r0.task.setChecked(True)
    r0.tasklist.setCurrentIndex(r0.tasklist.findData("L3"))
    got = []
    d.submitted.connect(got.append)
    d._submit()
    dec = got[0][0]
    assert dec.item.title == "수정된 제목" and dec.alarm_minutes == 5 and dec.item.all_day
    assert dec.targets == {"calendar", "task"} and dec.tasklist_id == "L3" and dec.item.category == "담임"


def test_settings_save_roundtrip(app):
    c = cfg.Config()
    dlg = SettingsDialog(c, tasklists=LISTS)
    dlg.provider.setCurrentIndex(list(dlg.provider.itemData(i) for i in range(dlg.provider.count())).index("claude"))
    dlg.api_key.setText("sk-test")
    dlg.model.setEditText("claude-opus-5")
    dlg.alarm_minutes.setValue(45)
    dlg.default_target.setCurrentIndex(3)
    dlg.inbox_name.setText("받은편지함")
    dlg.kind_rules.setPlainText("연수는 캘린더")
    dlg.category_rules.setPlainText("공문은 '학교'")
    dlg.coolm_enabled.setChecked(True)
    dlg.coolm_poll.setValue(60)
    dlg.coolm_dir.setText("/tmp/memo")
    assert "'학교'" in dlg.tasklist_names.text()
    saved = []
    dlg.saved.connect(saved.append)
    dlg._save()
    assert saved
    c2 = cfg.Config.load()
    assert c2.llm.provider == "claude" and c2.llm.model == "claude-opus-5"
    assert cfg.get_secret(cfg.SECRET_CLAUDE_API_KEY) == "sk-test"
    assert c2.schedule.alarm_minutes == 45 and c2.schedule.default_target == "both"
    assert c2.schedule.inbox_list_name == "받은편지함"
    assert c2.schedule.kind_rules == "연수는 캘린더" and c2.schedule.category_rules == "공문은 '학교'"
    assert c2.coolm.enabled and c2.coolm.poll_seconds == 60 and c2.coolm.memo_dir == "/tmp/memo"


def test_settings_google_disabled_without_auth(app):
    dlg = SettingsDialog(cfg.Config())
    assert not dlg.btn_login.isEnabled() and "v0.3" in dlg.google_status.text()
    assert dlg.TAB_INDEX["update"] == dlg.tabs.count() - 1
