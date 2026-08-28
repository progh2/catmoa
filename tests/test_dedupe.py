import os
from datetime import datetime

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from src import config as cfg
from src.extract.schema import ScheduleItem
from src.gsync.calendar import CalendarClient
from src.gsync.dedupe import find_duplicates, normalize, similarity
from src.gsync.registrar import Registrar
from src.gsync.tasks import TasksClient
from src.ui.dedupe_dialog import DedupeDialog
from src.ui.review_dialog import Decision
from tests.test_gsync_register import FakeService


def _ev(**kw):
    base = dict(title="제2회 학교운영위원회", start=datetime(2026, 9, 3, 14), end=datetime(2026, 9, 3, 16), kind="event")
    base.update(kw)
    return ScheduleItem(**base)


def _task(**kw):
    base = dict(title="혁신제품 실태조사 제출", start=datetime(2026, 9, 10), all_day=True, kind="task", end=None)
    base.update(kw)
    return ScheduleItem(**base)


# ---------------------------------------------------------------- 유사도

@pytest.mark.parametrize("a,b,expect", [
    ("제2회 학교운영위원회", "제2회 학교운영위원회", 1.0),
    ("학교운영위원회", "[9/3] 학교 운영위원회 (회의실)", 0.95),
    ("실태조사 제출", "혁신제품 실태조사 제출 (마감)", 0.95),
    ("교무회의", "학부모 상담", 0.0),
])
def test_similarity(a, b, expect):
    assert similarity(a, b) >= expect if expect else similarity(a, b) < 0.5
    assert normalize("  제출 안내 (마감) ") != ""


# ---------------------------------------------------------------- 매칭

def test_find_duplicates_calendar_and_task():
    svc = FakeService(
        events_data=[
            {"id": "e1", "summary": "학교운영위원회", "start": {"dateTime": "2026-09-03T14:00:00+09:00"}, "htmlLink": "https://cal/e1"},
            {"id": "e2", "summary": "학교운영위원회", "start": {"date": "2026-08-20"}},          # 날짜 멀어서 제외
            {"id": "e3", "summary": "완전히 다른 행사", "start": {"date": "2026-09-03"}},
        ],
        tasks_data={"L2": [{"id": "t9", "title": "혁신제품 실태조사 제출", "status": "needsAction", "due": "2026-09-11T00:00:00.000Z"},
                           {"id": "t8", "title": "실태조사 제출", "status": "needsAction", "due": "2026-10-01T00:00:00.000Z"}]},
    )
    ds = [Decision(_ev(), {"calendar"}, 15),
          Decision(_task(), {"task"}, None, tasklist_id="L2"),
          Decision(_ev(title="교무회의", start=datetime(2026, 9, 4, 10)), {"calendar"}, None)]
    r = find_duplicates(ds, cfg.ScheduleSettings(calendar_id="cal1"), calendar=CalendarClient(svc), tasks=TasksClient(svc))
    assert not r.errors and len(r.matches) == 2
    cal, tk = r.matches
    assert cal.target == "calendar" and cal.existing["id"] == "e1" and cal.link == "https://cal/e1" and cal.when.startswith("2026-09-03 14:00")
    assert tk.target == "task" and tk.existing["id"] == "t9" and tk.tasklist_id == "L2" and tk.when == "2026-09-11"
    # 캘린더 조회는 한 번, 기간은 항목 범위 ±
    lists = [c for c in svc.calls if c[0] == "events.list"]
    assert len(lists) == 1 and lists[0][1]["calendarId"] == "cal1" and lists[0][1]["timeMin"].startswith("2026-09-02")


def test_find_duplicates_errors_do_not_raise():
    class Boom:
        def list_events(self, *a, **k):
            raise RuntimeError("net")
    r = find_duplicates([Decision(_ev(), {"calendar"}, None)], cfg.ScheduleSettings(), calendar=Boom(), tasks=None)
    assert not r.matches and r.errors and "캘린더 조회 실패" in r.errors[0]


# ---------------------------------------------------------------- Registrar 처리

def test_registrar_skip_update_create():
    svc = FakeService()
    r = Registrar(auth=None, settings=cfg.ScheduleSettings(calendar_id="c"), calendar=CalendarClient(svc), tasks=TasksClient(svc))
    d_skip = Decision(_ev(), {"calendar"}, None, dedupe={"calendar": ("skip", {"id": "e1"}, "")})
    d_upd = Decision(_task(), {"task"}, None, tasklist_id="L2", dedupe={"task": ("update", {"id": "t9"}, "L2")})
    d_upd_cal = Decision(_ev(title="회의"), {"calendar"}, 10, dedupe={"calendar": ("update", {"id": "e5"}, "")})
    d_new = Decision(_ev(title="새 행사"), {"calendar"}, None, dedupe={"calendar": ("create", {"id": "e1"}, "")})
    rep = r.register([d_skip, d_upd, d_upd_cal, d_new])
    assert rep.ok
    names = [c[0] for c in svc.calls]
    assert names == ["tasks.patch", "events.patch", "events.insert"]
    assert svc.calls[0][1]["task"] == "t9" and svc.calls[0][1]["body"]["due"].startswith("2026-09-10")
    assert svc.calls[1][1]["eventId"] == "e5" and svc.calls[1][1]["body"]["reminders"]["overrides"][0]["minutes"] == 10
    assert "summary" not in svc.calls[1][1]["body"]            # 제목은 기존 유지
    assert "⏭📅" in rep.successes[0] and "🔄✅" in rep.successes[1] and "🔄📅" in rep.successes[2] and rep.successes[3].startswith("📅")


# ---------------------------------------------------------------- 다이얼로그

def test_dedupe_dialog_choices():
    app = QApplication.instance() or QApplication([])
    from src.gsync.dedupe import DupMatch
    ms = [DupMatch(Decision(_ev(), {"calendar"}, None), "calendar", {"id": "e1"}, 0.9, title="기존", when="2026-09-03"),
          DupMatch(Decision(_task(), {"task"}, None), "task", {"id": "t1"}, 0.8, tasklist_id="L2", title="기존T", when="2026-09-10")]
    dlg = DedupeDialog(ms)
    assert dlg.choices() == ["skip", "skip"]
    dlg._bulk("update")
    assert dlg.choices() == ["update", "update"]
    dlg.combos[1].setCurrentIndex(2)
    assert dlg.choices() == ["update", "create"]
    dlg.close()
