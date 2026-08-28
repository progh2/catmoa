from datetime import datetime

import pytest

from src import config as cfg
from src.extract.schema import ScheduleItem
from src.gsync.auth import GoogleAuthError
from src.gsync.calendar import CalendarClient, event_body
from src.gsync.registrar import ALL_DAY_DEADLINE_ALARM, Registrar
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


def _task(**kw):
    base = dict(title="제출", start=datetime(2026, 9, 10), all_day=True, kind="task", end=None)
    base.update(kw)
    return _event(**base)


# ---------------------------------------------------------------- body 생성

def test_event_body_timed_and_alarm():
    b = event_body(_event(), 30)
    assert b["summary"] == "회의" and b["location"] == "회의실"
    assert b["start"]["dateTime"].startswith("2026-09-03T14:00:00")
    assert b["end"]["dateTime"].startswith("2026-09-03T16:00:00")
    assert b["reminders"] == {"useDefault": False, "overrides": [{"method": "popup", "minutes": 30}]}
    assert "근거" in b["description"] and "공문.hwp" in b["description"]


def test_event_body_all_day_range_and_no_alarm():
    b = event_body(_event(all_day=True, start=datetime(2026, 9, 1), end=datetime(2026, 9, 5)), None)
    assert b["start"] == {"date": "2026-09-01"} and b["end"] == {"date": "2026-09-06"}
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
    assert "notes" not in task_body(ScheduleItem(title="x", start=datetime(2026, 9, 10), all_day=True, kind="task"))


# ---------------------------------------------------------------- 클라이언트

def test_tasks_client_find_list_create():
    svc = FakeService()
    t = TasksClient(svc)
    assert t.find_tasklist(" 인박스 ") == ("L2", "인박스")
    assert t.find_tasklist("없음") is None
    assert [x["id"] for x in t.list_open_tasks("L2")] == ["t1"]
    t.complete_task("L2", "t1")
    assert svc.calls[-1] == ("tasks.patch", {"tasklist": "L2", "task": "t1", "body": {"status": "completed"}})
    t.create_tasklist("새목록")
    assert svc.calls[-1][0] == "tasklists.insert"


# ---------------------------------------------------------------- Registrar

def _registrar(settings=None, svc=None, tasklists=None):
    svc = svc or FakeService()
    s = settings or cfg.ScheduleSettings()
    r = Registrar(auth=None, settings=s, calendar=CalendarClient(svc), tasks=TasksClient(svc), tasklists=tasklists)
    return r, svc


def _names(svc):
    return [c[0] for c in svc.calls]


def test_register_calendar_only_and_task_only_with_alarm_event():
    r, svc = _registrar(cfg.ScheduleSettings(task_alarm_as_event=True, calendar_id="cal1", tasklist_id="L2"))
    rep = r.register([
        Decision(_event(), {"calendar"}, 15),
        Decision(_task(), {"task"}, 60),
        Decision(_task(title="알람없음"), {"task"}, None),
    ])
    assert rep.ok and len(rep.successes) == 3
    assert _names(svc) == ["events.insert", "tasks.insert", "events.insert", "tasks.insert"]
    assert svc.calls[0][1]["calendarId"] == "cal1"
    assert svc.calls[1][1]["tasklist"] == "L2"
    alarm_ev = svc.calls[2][1]["body"]
    assert alarm_ev["summary"] == "⏰ 제출" and alarm_ev["start"]["dateTime"].startswith("2026-09-10T09:00")
    assert alarm_ev["reminders"]["overrides"][0]["minutes"] == 60
    assert "⏰" in rep.successes[1] and "⏰" not in rep.successes[2]


def test_register_both_task_item_makes_deadline_event():
    r, svc = _registrar(cfg.ScheduleSettings(task_alarm_as_event=True))
    rep = r.register([Decision(_task(), {"calendar", "task"}, 30, tasklist_id="L9", tasklist_name="학교")])
    assert rep.ok and _names(svc) == ["tasks.insert", "events.insert"]
    assert svc.calls[0][1]["tasklist"] == "L9"
    ev = svc.calls[1][1]["body"]
    assert ev["summary"] == "제출 (마감)" and ev["start"] == {"date": "2026-09-10"}
    assert ev["reminders"]["overrides"][0]["minutes"] == ALL_DAY_DEADLINE_ALARM   # 전날 17:00
    assert "✅[학교]" in rep.successes[0] and "📅(마감)" in rep.successes[0]


def test_register_both_event_item_makes_normal_event_and_timed_deadline_alarm():
    r, svc = _registrar()
    rep = r.register([Decision(_event(), {"calendar", "task"}, 10)])
    assert rep.ok and _names(svc) == ["tasks.insert", "events.insert"]
    assert svc.calls[1][1]["body"]["summary"] == "회의"            # event 성격 → 일반 일정
    # 시각이 있는 task 는 마감 일정도 시각 그대로 + 사용자 알람 분
    r2, svc2 = _registrar()
    r2.register([Decision(_task(all_day=False, start=datetime(2026, 9, 10, 17)), {"calendar", "task"}, 10)])
    ev = svc2.calls[1][1]["body"]
    assert ev["start"]["dateTime"].startswith("2026-09-10T17:00") and ev["reminders"]["overrides"][0]["minutes"] == 10


def test_register_category_name_maps_to_tasklist():
    r, svc = _registrar(cfg.ScheduleSettings(tasklist_id="DEF"), tasklists={"학교 업무": "L7"})
    r.register([Decision(_task(category="학교업무"), {"task"}, None),
                Decision(_task(category="없는목록"), {"task"}, None)])
    assert svc.calls[0][1]["tasklist"] == "L7" and svc.calls[1][1]["tasklist"] == "DEF"


def test_register_task_alarm_disabled_setting():
    r, svc = _registrar(cfg.ScheduleSettings(task_alarm_as_event=False))
    rep = r.register([Decision(_event(kind="task"), {"task"}, 10)])
    assert rep.ok and _names(svc) == ["tasks.insert"]


def test_register_partial_failure_and_origin_complete():
    r, svc = _registrar(cfg.ScheduleSettings(complete_inbox_after_import=True))
    rep = r.register([Decision(_event(title="FAIL"), {"calendar"}, None), Decision(_event(), {"calendar"}, None)],
                     origin_task=("L2", "t1"))
    assert len(rep.successes) == 1 and len(rep.failures) == 1 and "boom" in rep.failures[0]
    assert rep.completed_origin and svc.calls[-1][0] == "tasks.patch"
    assert "↩" in rep.summary()


def test_register_auth_error_stops():
    class BadCal:
        def create_event(self, *a, **k):
            raise GoogleAuthError("로그인 필요")
    r = Registrar(auth=None, settings=cfg.ScheduleSettings(), calendar=BadCal(), tasks=None)
    rep = r.register([Decision(_event(), {"calendar"}, None), Decision(_event(), {"calendar"}, None)])
    assert len(rep.failures) == 1 and not rep.successes
