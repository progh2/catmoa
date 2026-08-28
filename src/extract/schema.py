"""일정 추출 결과 스키마.

LLM에게는 단순한 문자열 필드(date/time)를 요구하고, 여기서 datetime으로 정규화한다.
"""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

Kind = Literal["event", "task"]


class RawItem(BaseModel):
    """LLM이 반환하는 항목 형태 (관대하게 받는다)."""
    title: str
    date: str | None = None          # YYYY-MM-DD
    time: str | None = None          # HH:MM
    end_date: str | None = None
    end_time: str | None = None
    kind: str | None = "event"
    category: str | None = None      # 태스크 카테고리(Google Tasks 목록 이름)
    location: str | None = None
    notes: str | None = None
    confidence: float | None = 0.8

    @field_validator("title")
    @classmethod
    def _title(cls, v: str) -> str:
        v = " ".join(str(v).split())
        if not v:
            raise ValueError("제목 없음")
        return v[:200]


class ScheduleItem(BaseModel):
    """앱 내부 표준 항목. 검토 다이얼로그·Google 등록에서 사용."""
    title: str
    start: datetime
    end: datetime | None = None
    all_day: bool = False
    kind: Kind = "event"
    category: str | None = None           # 제안된 태스크 목록 이름
    location: str | None = None
    notes: str | None = None
    alarm_minutes: int | None = None     # None = 알람 없음 (기본값은 설정에서 채움)
    confidence: float = Field(0.8, ge=0.0, le=1.0)
    source: str = ""                      # 출처 표시 ("공문.hwp", "쿨메신저: 홍길동")
    undated: bool = False                 # 날짜 없는 할 일(todo). start 는 기준일 자리표시, 캘린더 등록 불가

    @model_validator(mode="after")
    def _fix_end(self):
        if self.end is not None and self.end < self.start:
            self.end = None
        if self.all_day:
            self.start = datetime.combine(self.start.date(), time.min)
            if self.end is not None:
                self.end = datetime.combine(self.end.date(), time.min)
        return self

    @property
    def start_date(self) -> date:
        return self.start.date()

    def describe_when(self) -> str:
        if self.undated:
            return "날짜 없음"
        if self.all_day:
            s = self.start.strftime("%Y-%m-%d")
            if self.end and self.end.date() != self.start.date():
                return f"{s} ~ {self.end.strftime('%Y-%m-%d')}"
            return s
        s = self.start.strftime("%Y-%m-%d %H:%M")
        if self.end:
            if self.end.date() == self.start.date():
                return f"{s}~{self.end.strftime('%H:%M')}"
            return f"{s} ~ {self.end.strftime('%Y-%m-%d %H:%M')}"
        return s


# ---------------------------------------------------------------- 정규화

_DATE_RE = re.compile(r"(\d{4})[-./년]\s*(\d{1,2})[-./월]\s*(\d{1,2})")
_TIME_RE = re.compile(r"(\d{1,2})[:시]\s*(\d{1,2})?")


def parse_date(s: str | None, ref: date) -> date | None:
    if not s:
        return None
    s = str(s).strip()
    m = _DATE_RE.search(s)
    if m:
        y, mo, d = (int(x) for x in m.groups())
        try:
            return date(y, mo, d)
        except ValueError:
            return None
    # MM-DD / M/D 만 있으면 기준일과 가장 가까운 미래
    m = re.search(r"(\d{1,2})[-./월]\s*(\d{1,2})", s)
    if m:
        mo, d = int(m.group(1)), int(m.group(2))
        for y in (ref.year, ref.year + 1):
            try:
                cand = date(y, mo, d)
            except ValueError:
                continue
            if cand >= ref - timedelta(days=30):
                return cand
    return None


def parse_time(s: str | None) -> time | None:
    if not s:
        return None
    s = str(s).strip().lower()
    if s in ("", "null", "none", "종일", "all day", "all-day"):
        return None
    pm = "오후" in s or "pm" in s
    am = "오전" in s or "am" in s
    m = _TIME_RE.search(s)
    if not m:
        return None
    h = int(m.group(1))
    mi = int(m.group(2) or 0)
    if pm and h < 12:
        h += 12
    if am and h == 12:
        h = 0
    if not (0 <= h <= 23 and 0 <= mi <= 59):
        return None
    return time(h, mi)


def normalize(raw: RawItem, ref: date, source: str = "") -> ScheduleItem | None:
    """RawItem → ScheduleItem. 날짜가 없으면: task 는 '날짜 없는 할 일'로 유지, event 는 None."""
    kind: Kind = "task" if str(raw.kind or "").lower().startswith("task") else "event"
    d = parse_date(raw.date, ref)
    if d is None:
        if kind != "task":
            return None
        conf = raw.confidence if isinstance(raw.confidence, (int, float)) else 0.8
        try:
            return ScheduleItem(
                title=raw.title, start=datetime.combine(ref, time.min), all_day=True, kind="task", undated=True,
                category=(raw.category or None) and str(raw.category).strip()[:100] or None,
                notes=(raw.notes or None) and str(raw.notes).strip()[:2000] or None,
                confidence=max(0.0, min(1.0, float(conf))), source=source,
            )
        except ValidationError:
            return None
    t = parse_time(raw.time)
    ed = parse_date(raw.end_date, ref)
    et = parse_time(raw.end_time)
    all_day = t is None
    start = datetime.combine(d, t or time.min)
    end: datetime | None = None
    if ed is not None or et is not None:
        end = datetime.combine(ed or d, et or (t or time.min))
        if not all_day and et is None and ed is not None:
            end = datetime.combine(ed, t)  # 종료일만 있고 시간 없으면 같은 시각
    conf = raw.confidence if isinstance(raw.confidence, (int, float)) else 0.8
    try:
        return ScheduleItem(
            title=raw.title,
            start=start,
            end=end,
            all_day=all_day,
            kind=kind,
            category=(raw.category or None) and str(raw.category).strip()[:100] or None,
            location=(raw.location or None) and str(raw.location).strip()[:200] or None,
            notes=(raw.notes or None) and str(raw.notes).strip()[:2000] or None,
            confidence=max(0.0, min(1.0, float(conf))),
            source=source,
        )
    except ValidationError:
        return None
