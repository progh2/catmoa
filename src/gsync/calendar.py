"""Google Calendar 이벤트 생성."""
from __future__ import annotations

from datetime import datetime, timedelta

from src.extract.schema import ScheduleItem


def _local_iso(dt: datetime) -> str:
    """naive datetime 은 로컬 시간대로 간주해 오프셋 포함 ISO 문자열로."""
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt.isoformat()


def event_body(item: ScheduleItem, alarm_minutes: int | None, *, title: str | None = None,
               description_extra: str = "") -> dict:
    desc_parts = []
    if item.notes:
        desc_parts.append(item.notes)
    if item.source:
        desc_parts.append(f"출처: {item.source}")
    if description_extra:
        desc_parts.append(description_extra)
    desc_parts.append("catmoa 🐱 로 등록")
    body: dict = {
        "summary": title or item.title,
        "description": "\n".join(desc_parts),
        "reminders": {"useDefault": False, "overrides": []},
    }
    if item.location:
        body["location"] = item.location
    if item.all_day:
        start_d = item.start.date()
        end_d = (item.end.date() if item.end else start_d) + timedelta(days=1)   # 종료일은 배타적
        body["start"] = {"date": start_d.isoformat()}
        body["end"] = {"date": end_d.isoformat()}
    else:
        end = item.end or (item.start + timedelta(hours=1))
        body["start"] = {"dateTime": _local_iso(item.start)}
        body["end"] = {"dateTime": _local_iso(end)}
    if alarm_minutes is not None:
        body["reminders"]["overrides"] = [{"method": "popup", "minutes": int(alarm_minutes)}]
    return body


class CalendarClient:
    def __init__(self, service):
        self.svc = service

    def create_event(self, item: ScheduleItem, calendar_id: str = "primary", alarm_minutes: int | None = None,
                     **kw) -> dict:
        body = event_body(item, alarm_minutes, **kw)
        return self.svc.events().insert(calendarId=calendar_id or "primary", body=body).execute()
