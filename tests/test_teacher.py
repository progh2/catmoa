import json
import os
from datetime import date

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from src import config as cfg
from src.extract import Extractor
from src.extract.prompts import user_prompt
from src.parsers import ParsedInput
from tests.test_extract import FakeProvider


def test_teacher_defaults_and_describe():
    t = cfg.TeacherSettings()
    d = t.describe()
    assert "출근 08:30" in d and "퇴근(퇴청) 16:30" in d and "1교시 09:00~09:45" in d and "점심시간 12:30~13:20" in d
    t.enabled = False
    assert t.describe() == ""


def test_autofill_middle_school():
    t = cfg.TeacherSettings(period_minutes=45, break_minutes=10)
    t.autofill(first="09:00")
    assert t.periods == ["09:00", "09:55", "10:50", "11:45", "13:20", "14:15", "15:10"]
    assert t.lunch_start == "12:30" and t.lunch_end == "13:20"
    e = cfg.TeacherSettings(period_minutes=40, break_minutes=10)
    e.autofill(first="09:00")
    assert e.periods[1] == "09:50" and e.lunch_start == "12:10"


def test_config_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("CATMOA_CONFIG_DIR", str(tmp_path))
    c = cfg.Config()
    c.teacher.school_level = "high"; c.teacher.period_minutes = 50; c.teacher.work_end = "17:00"
    c.teacher.periods[0] = "08:50"
    c.save()
    c2 = cfg.Config.load()
    assert c2.teacher.school_level == "high" and c2.teacher.period_minutes == 50 and c2.teacher.periods[0] == "08:50"


def test_prompt_and_extractor_pass_timetable():
    tt = cfg.TeacherSettings().describe()
    p = user_prompt("x", date(2026, 6, 8), timetable=tt)
    assert "시간표 참고" in p and "3교시" in p
    assert "시간표 참고" not in user_prompt("x", date(2026, 6, 8))
    prov = FakeProvider([json.dumps({"items": [{"title": "회의", "date": "2026-06-09", "time": "16:30"}]})])
    Extractor(prov).extract(ParsedInput(text="x"), date(2026, 6, 8), timetable=tt)
    assert "퇴근(퇴청) 16:30" in prov.calls[0].text


def test_settings_teacher_tab(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication
    from src.ui.settings_dialog import SettingsDialog
    QApplication.instance() or QApplication([])
    monkeypatch.setenv("CATMOA_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("CATMOA_NO_KEYRING", "1")
    c = cfg.Config()
    dlg = SettingsDialog(c)
    assert dlg.tabs.tabText(dlg.TAB_INDEX["teacher"]) == "교사"
    dlg.tt_level.setCurrentIndex(list(cfg.SCHOOL_LABELS).index("high"))
    assert dlg.tt_period.value() == 50
    dlg.tt_periods[0].setTime(dlg._qtime("08:50"))
    dlg._tt_autofill()
    assert dlg.tt_periods[1].time().toString("HH:mm") == "09:50"
    assert "AI에 전달되는 시간표" in dlg.tt_preview.text() and "1교시 08:50~09:40" in dlg.tt_preview.text()
    dlg.tt_work_end.setTime(dlg._qtime("16:40"))
    dlg._save()
    c2 = cfg.Config.load()
    assert c2.teacher.school_level == "high" and c2.teacher.period_minutes == 50
    assert c2.teacher.periods[0] == "08:50" and c2.teacher.work_end == "16:40"


# ---------------------------------------------------------------- 교시 연쇄 계산 (#54)

def test_cascade_morning_block_only():
    """1교시를 고치면 2~4교시만 따라온다 (오후는 그대로)."""
    t = cfg.TeacherSettings(period_minutes=45, break_minutes=10,
                            periods=["09:00", "09:55", "10:50", "11:45", "13:30", "14:25", "15:20"])
    t.periods[0] = "08:40"
    t.cascade(0)
    assert t.periods[:4] == ["08:40", "09:35", "10:30", "11:25"]
    assert t.periods[4:] == ["13:30", "14:25", "15:20"]          # 오후는 건드리지 않는다
    assert t.lunch_start == "12:10" and t.lunch_end == "13:30"   # 4교시 종료 ~ 5교시 시작


def test_cascade_afternoon_block_only():
    t = cfg.TeacherSettings(period_minutes=45, break_minutes=10)
    before = list(t.periods[:4])
    t.periods[4] = "13:10"
    t.cascade(4)
    assert t.periods[:4] == before
    assert t.periods[4:] == ["13:10", "14:05", "15:00"]
    assert t.lunch_end == "13:10"


def test_cascade_from_middle_of_block():
    """3교시를 고치면 4교시만 따라오고 1·2교시는 그대로."""
    t = cfg.TeacherSettings(period_minutes=50, break_minutes=10)
    t.periods[2] = "11:00"
    t.cascade(2)
    assert t.periods[:2] == ["09:00", "09:55"] and t.periods[2:4] == ["11:00", "12:00"]
    assert t.lunch_start == "12:50"


def test_cascade_all_on_period_length_change():
    t = cfg.TeacherSettings(period_minutes=40, break_minutes=10)   # 초등
    t.cascade_all()
    assert t.periods[:4] == ["09:00", "09:50", "10:40", "11:30"]
    assert t.periods[4:] == ["13:30", "14:20", "15:10"]
    assert t.lunch_start == "12:10" and t.lunch_end == "13:30"


def test_lunch_auto_off_keeps_manual_values():
    t = cfg.TeacherSettings(lunch_auto=False, lunch_start="12:00", lunch_end="12:50")
    t.cascade(0)
    assert t.lunch_start == "12:00" and t.lunch_end == "12:50"


def test_lunch_never_reversed():
    """오전이 너무 늦게 끝나면 점심 길이가 0 이 될 뿐, 오후를 밀지는 않는다."""
    t = cfg.TeacherSettings(period_minutes=45, break_minutes=10)
    t.periods[0] = "12:00"
    t.cascade(0)
    assert t.periods[4] == "13:30" and t.lunch_start == t.lunch_end == "15:30"


def test_settings_dialog_cascades_widgets(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication
    from src.ui.settings_dialog import SettingsDialog

    monkeypatch.setenv("CATMOA_CONFIG_DIR", str(tmp_path))
    QApplication.instance() or QApplication([])
    c = cfg.Config()
    dlg = SettingsDialog(c)
    dlg.tt_periods[0].setTime(dlg._qtime("08:40"))
    assert [te.time().toString("HH:mm") for te in dlg.tt_periods[:4]] == ["08:40", "09:35", "10:30", "11:25"]
    assert dlg.tt_lunch_start.time().toString("HH:mm") == "12:10"
    assert not dlg.tt_lunch_start.isEnabled()                       # 자동일 땐 직접 못 고침

    dlg.tt_periods[4].setTime(dlg._qtime("13:00"))
    assert [te.time().toString("HH:mm") for te in dlg.tt_periods[4:]] == ["13:00", "13:55", "14:50"]
    assert dlg.tt_lunch_end.time().toString("HH:mm") == "13:00"

    dlg.tt_period.setValue(50)                                      # 수업 시간 변경 → 두 블록 모두 재계산
    assert [te.time().toString("HH:mm") for te in dlg.tt_periods[:4]] == ["08:40", "09:40", "10:40", "11:40"]
    assert dlg.tt_lunch_auto.isChecked()
    dlg.tt_lunch_auto.setChecked(False)
    assert dlg.tt_lunch_start.isEnabled()
    dlg._save()
    assert c.teacher.lunch_auto is False and c.teacher.periods[1] == "09:40"
