from datetime import datetime

import pytest

from src import config as cfg
from src.extract.schema import ScheduleItem
from src.gsync.auth import GoogleAuthError
from src.gsync.calendar import CalendarClient, event_body
from src.gsync.registrar import Registrar
from src.gsync.tasks import TasksClient, task_body
from src.ui.review_dialog import Decision


# ---------------------------------------------------------------- 가짜 Google 서비스

class _Call:
    def __init__(self, store, name, **kw):
        self.store, self.name, self.kw = store, name, kw

    def execute(self):
        self.store.append((self.name, self.kw))
        if self.name == "tasklists.list":
            return {"items": [{"id": "L1", "title": "내 할 일"}, {"id": "L2", "title": "인박스"}]}
        if self.name == "tasks.list":
            return {"items": [{"id": "t1", "title": "금요일 가정통신문", "status": "needsAction"},
                              {"id": "t2", "title": "", "status": "needsAction"},
                              {"id": "t3", "title": "done", "status": "completed"}]}
        if self.name == "events.insert" and self.kw["body"]["summary"] == "FAIL":
            raise RuntimeError("boom")
        return {"id": f"{self.name}-id", "htmlLink": "https://x"}


class _Res:
    def __init__(self, store, prefix):
        self.store, self.prefix = store, prefix

    def __getattr__(self, method):
        return lambda **kw: _Call(self.store, f"{self.prefix}.{method}", **kw)


class FakeService:
    def __init__(self):
        self.calls = []

    def events(self):
        return _Res(self.calls, "events")

    def tasks(self):
        return _Res(self.calls, "tasks")

    def tasklists(self):
        return _Res(self.calls, "tasklists")


def _event(**kw):
    base = dict(title="회의", start=datetime(2026, 9, 3, 14), end=datetime(2026, 9, 3, 16), kind="event",
                location="회의실", notes="근거", source="공문.hwp")
    base.update(kw)
    return ScheduleItem(**base)


# ---------------------------------------------------------------- body 생성

def test_event_body_timed_and_alarm():
    b = event_body(_event(), 30)
    assert b["summary"] == "회의" and b["location"] == "회의실"
    assert b["start"]["dateTime"].startswith("2026-09-03T14:00:00") and "+" in b["start"]["dateTime"] or "-" in b["start"]["dateTime"][19:]
    assert b["end"]["dateTime"].startswith("2026-09-03T16:00:00")
    assert b["reminders"] == {"useDefault": False, "overrides": [{"method": "popup", "minutes": 30}]}
    assert "근거" in b["description"] and "공문.hwp" in b["description"]


def test_event_body_all_day_range_and_no_alarm():
    b = event_body(_event(all_day=True, start=datetime(2026, 9, 1), end=datetime(2026, 9, 5)), None)
    assert b["start"] == {"date": "2026-09-01"} and b["end"] == {"date": "2026-09-06"}   # 배타적 종료
    assert b["reminders"]["overrides"] == []
    b2 = event_body(_event(all_day=True, start=datetime(2026, 9, 1), end=None), None)
    assert b2["end"] == {"date": "2026-09-02"}


def test_event_body_default_end():
    b = event_body(_event(end=None), None)
    assert b["end"]["dateTime"].startswith("2026-09-03T15:00:00")


def test_task_body():
    b = task_body(_event(kind="task", all_day=False))
    assert b["title"] == "회의" and b["due"] == "2026-09-03T00:00:00.000Z"
    assert "시각: 14:00" in b["notes"] and "장소: 회의실" in b["notes"]
    b2 = task_body(ScheduleItem(title="x", start=datetime(2026, 9, 10), all_day=True, kind="task"))
    assert "notes" not in b2


# ---------------------------------------------------------------- 클라이언트

def test_tasks_client_find_and_list():
    svc = FakeService()
    t = TasksClient(svc)
    assert t.find_tasklist(" 인박스 ") == ("L2", "인박스")
    assert t.find_tasklist("없음") is None
    opens = t.list_open_tasks("L2")
    assert [x["id"] for x in opens] == ["t1"]
    t.complete_task("L2", "t1")
    assert svc.calls[-1] == ("tasks.patch", {"tasklist": "L2", "task": "t1", "body": {"status": "completed"}})


# ---------------------------------------------------------------- Registrar

def _registrar(settings=None, svc=None):
    svc = svc or FakeService()
    s = settings or cfg.ScheduleSettings()
    r = Registrar(auth=None, settings=s, calendar=CalendarClient(svc), tasks=TasksClient(svc))
    return r, svc


def test_register_calendar_and_task_with_alarm_event():
    r, svc = _registrar(cfg.ScheduleSettings(task_alarm_as_event=True, calendar_id="cal1", tasklist_id="L2"))
    ds = [
        Decision(_event(), "calendar", 15),
        Decision(_event(title="제출", kind="task", all_day=True, start=datetime(2026, 9, 10), end=None), "task", 60),
        Decision(_event(title="알람없음", kind="task"), "task", None),
    ]
    rep = r.register(ds)
    assert rep.ok and len(rep.successes) == 3
    names = [c[0] for c in svc.calls]
    assert names == ["events.insert", "tasks.insert", "events.insert", "tasks.insert"]
    assert svc.calls[0][1]["calendarId"] == "cal1"
    assert svc.calls[1][1]["tasklist"] == "L2"
    alarm_ev = svc.calls[2][1]["body"]
    assert alarm_ev["summary"] == "⏰ 제출" and alarm_ev["start"]["dateTime"].startswith("2026-09-10T09:00")
    assert alarm_ev["reminders"]["overrides"][0]["minutes"] == 60
    assert "(+알림 이벤트)" in rep.successes[1]


def test_register_task_alarm_disabled_setting():
    r, svc = _registrar(cfg.ScheduleSettings(task_alarm_as_event=False))
    rep = r.register([Decision(_event(kind="task"), "task", 10)])
    assert rep.ok and [c[0] for c in svc.calls] == ["tasks.insert"]


def test_register_partial_failure_and_origin_complete():
    r, svc = _registrar(cfg.ScheduleSettings(complete_inbox_after_import=True))
    rep = r.register([Decision(_event(title="FAIL"), "calendar", None), Decision(_event(), "calendar", None)],
                     origin_task=("L2", "t1"))
    assert len(rep.successes) == 1 and len(rep.failures) == 1 and "boom" in rep.failures[0]
    assert rep.completed_origin and svc.calls[-1][0] == "tasks.patch"
    assert "↩" in rep.summary()


def test_register_auth_error_stops():
    class BadCal:
        def create_event(self, *a, **k):
            raise GoogleAuthError("로그인 필요")
    r = Registrar(auth=None, settings=cfg.ScheduleSettings(), calendar=BadCal(), tasks=None)
    rep = r.register([Decision(_event(), "calendar", None), Decision(_event(), "calendar", None)])
    assert len(rep.failures) == 1 and not rep.successes
