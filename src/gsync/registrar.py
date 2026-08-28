"""검토 결과(Decision)를 Google Calendar / Tasks 에 등록한다. 블로킹 — 호출자가 스레드에서 실행.

대상 조합:
- 📅만: 캘린더 이벤트 (+알람)
- ✅만: 태스크 (+ 알람 선택 시 설정에 따라 캘린더 알림 이벤트)
- 📅+✅: 태스크(할 일) + 캘린더. 항목이 task 성격이면 캘린더엔 "(마감)" 종일 일정,
        event 성격이면 일반 일정. 종일 마감 일정의 알람은 전날 17:00 (Google 종일 알림 관례).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, time

from src import config as cfg
from src.gsync.auth import GoogleAuth, GoogleAuthError
from src.gsync.calendar import CalendarClient
from src.gsync.tasks import TasksClient
from src.ui.review_dialog import Decision

log = logging.getLogger(__name__)

TASK_ALARM_HOUR = 9            # 태스크 알림 이벤트 기본 시각
ALL_DAY_DEADLINE_ALARM = 7 * 60  # 종일 마감 일정 알림: 전날 17:00


@dataclass
class RegistrationReport:
    successes: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    completed_origin: bool = False

    @property
    def ok(self) -> bool:
        return not self.failures

    def summary(self) -> str:
        lines = [f"✅ {s}" for s in self.successes] + [f"❌ {f}" for f in self.failures]
        if self.completed_origin:
            lines.append("↩ 인박스 원본을 완료 처리했습니다.")
        return "\n".join(lines) if lines else "등록할 항목이 없습니다."


class Registrar:
    def __init__(self, auth: GoogleAuth, settings: cfg.ScheduleSettings, *,
                 calendar: CalendarClient | None = None, tasks: TasksClient | None = None,
                 tasklists: dict[str, str] | None = None):
        self.auth = auth
        self.settings = settings
        self._cal = calendar
        self._tasks = tasks
        self.tasklists = tasklists or {}   # 이름 → id (카테고리 매핑)

    @property
    def cal(self) -> CalendarClient:
        if self._cal is None:
            self._cal = CalendarClient(self.auth.calendar_service())
        return self._cal

    @property
    def tasks(self) -> TasksClient:
        if self._tasks is None:
            self._tasks = TasksClient(self.auth.tasks_service())
        return self._tasks

    def _tasklist_for(self, d: Decision) -> tuple[str, str]:
        """(id, 표시명). 우선순위: 검토창 선택 > 항목 category 이름 매핑 > 설정 기본."""
        if d.tasklist_id:
            return d.tasklist_id, d.tasklist_name
        cat = d.item.category
        if cat:
            key = "".join(cat.split()).lower()
            for name, tid in self.tasklists.items():
                if "".join(name.split()).lower() == key:
                    return tid, name
        return self.settings.tasklist_id, ""

    def register(self, decisions: list[Decision], *, origin_task: tuple[str, str] | None = None) -> RegistrationReport:
        rep = RegistrationReport()
        s = self.settings
        for d in decisions:
            item, when = d.item, d.item.describe_when()
            want_cal, want_task = "calendar" in d.targets, "task" in d.targets
            cal_dd = d.dedupe.get("calendar")      # (action, existing, tasklist_id) | None
            task_dd = d.dedupe.get("task")
            try:
                parts = []
                if want_task:
                    tid, tname = self._tasklist_for(d)
                    if task_dd and task_dd[0] == "skip":
                        parts.append("⏭✅(중복 건너뜀)")
                    elif task_dd and task_dd[0] == "update":
                        self.tasks.update_task(task_dd[2] or tid, task_dd[1]["id"], item)
                        parts.append("🔄✅(기존 갱신)")
                    else:
                        self.tasks.create_task(item, tid)
                        parts.append("✅" + (f"[{tname}]" if tname else ""))
                if want_cal and cal_dd and cal_dd[0] == "skip":
                    parts.append("⏭📅(중복 건너뜀)")
                elif want_cal and cal_dd and cal_dd[0] == "update":
                    self.cal.update_event(s.calendar_id, cal_dd[1]["id"], item, d.alarm_minutes)
                    parts.append("🔄📅(기존 갱신)")
                elif want_cal:
                    if want_task and item.kind == "task":
                        # 마감일 일정
                        alarm = None
                        if d.alarm_minutes is not None:
                            alarm = ALL_DAY_DEADLINE_ALARM if item.all_day else d.alarm_minutes
                        self.cal.create_event(item, s.calendar_id, alarm, title=f"{item.title} (마감)",
                                              description_extra="Google Tasks 할 일의 마감일")
                        parts.append("📅(마감)")
                    else:
                        ev = self.cal.create_event(item, s.calendar_id, d.alarm_minutes)
                        parts.append("📅")
                        log.info("캘린더 등록: %s", ev.get("htmlLink", ev.get("id")))
                elif want_task and d.alarm_minutes is not None and s.task_alarm_as_event and not item.undated:
                    self.cal.create_event(_alarm_event_item(item), s.calendar_id, d.alarm_minutes,
                                          title=f"⏰ {item.title}", description_extra="Google Tasks 마감 알림용 이벤트")
                    parts.append("⏰")
                rep.successes.append(f"{' '.join(parts)} {when}  {item.title}")
            except GoogleAuthError as e:
                rep.failures.append(f"{item.title}: {e}")
                break
            except Exception as e:  # noqa: BLE001
                log.exception("등록 실패: %s", item.title)
                rep.failures.append(f"{item.title}: {_friendly(e)}")

        if origin_task and rep.successes and s.complete_inbox_after_import:
            try:
                self.tasks.complete_task(*origin_task)
                rep.completed_origin = True
            except Exception as e:  # noqa: BLE001
                rep.failures.append(f"인박스 원본 완료 처리 실패: {_friendly(e)}")
        return rep


def _alarm_event_item(item):
    """태스크 알림용 이벤트: 시간이 없으면 마감일 09:00, 30분짜리."""
    start = datetime.combine(item.start.date(), time(TASK_ALARM_HOUR, 0)) if item.all_day else item.start
    return item.model_copy(update={"all_day": False, "start": start, "end": None,
                                   "notes": (item.notes or "") + ("\n" if item.notes else "") + "마감 알림"})


def _friendly(e: Exception) -> str:
    try:
        from googleapiclient.errors import HttpError

        if isinstance(e, HttpError):
            code = e.resp.status if getattr(e, "resp", None) else "?"
            if code == 401:
                return "인증이 만료되었습니다. 다시 로그인하세요."
            if code == 403:
                return "권한이 없습니다 (API 미활성화 또는 스코프 부족)."
            if code == 404:
                return "캘린더/목록을 찾을 수 없습니다. 설정에서 다시 선택하세요."
            return f"Google API 오류 ({code})"
    except ImportError:  # pragma: no cover
        pass
    return f"{type(e).__name__}: {e}"
