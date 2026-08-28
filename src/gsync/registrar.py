"""검토 결과(Decision)를 Google Calendar / Tasks 에 등록한다. 블로킹 — 호출자가 스레드에서 실행."""
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

TASK_ALARM_HOUR = 9   # 종일 태스크의 알림 이벤트 기본 시각


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
                 calendar: CalendarClient | None = None, tasks: TasksClient | None = None):
        self.auth = auth
        self.settings = settings
        self._cal = calendar
        self._tasks = tasks

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

    def register(self, decisions: list[Decision], *, origin_task: tuple[str, str] | None = None) -> RegistrationReport:
        """origin_task=(tasklist_id, task_id) 면 성공 후 원본 완료 처리 (설정에 따라)."""
        rep = RegistrationReport()
        s = self.settings
        for d in decisions:
            item, when = d.item, d.item.describe_when()
            try:
                if d.target == "calendar":
                    ev = self.cal.create_event(item, s.calendar_id, d.alarm_minutes)
                    rep.successes.append(f"📅 {when}  {item.title}")
                    log.info("캘린더 등록: %s", ev.get("htmlLink", ev.get("id")))
                else:
                    self.tasks.create_task(item, s.tasklist_id)
                    msg = f"✅ {when}  {item.title}"
                    if d.alarm_minutes is not None and s.task_alarm_as_event:
                        self.cal.create_event(_alarm_event_item(item), s.calendar_id, d.alarm_minutes,
                                              title=f"⏰ {item.title}", description_extra="Google Tasks 마감 알림용 이벤트")
                        msg += "  (+알림 이벤트)"
                    rep.successes.append(msg)
            except GoogleAuthError as e:
                rep.failures.append(f"{item.title}: {e}")
                break   # 인증 문제면 나머지도 실패하므로 중단
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
    if item.all_day:
        start = datetime.combine(item.start.date(), time(TASK_ALARM_HOUR, 0))
    else:
        start = item.start
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
