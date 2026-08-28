"""등록 전 중복 검사.

- 캘린더: 항목 날짜 전후(±1일, 기간이면 기간 전체)의 이벤트와 제목 유사도 비교
- 태스크: 대상 목록의 미완료 태스크와 제목 유사도 + 마감일 근접(±3일 또는 마감 없음) 비교
유사도: 공백·기호 제거 후 완전 일치/포함 → 1.0, 아니면 difflib 비율. 임계값 0.75.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher

from src import config as cfg
from src.gsync.calendar import CalendarClient
from src.gsync.tasks import TasksClient
from src.ui.review_dialog import Decision

log = logging.getLogger(__name__)

THRESHOLD = 0.75
_STRIP_RE = re.compile(r"[\s\[\]\(\)【】\-–—_:：·.,!?~〜\"'“”‘’]+")
_NOISE_RE = re.compile(r"(\(마감\)|⏰|마감|제출|안내|건|관련)")


def normalize(title: str) -> str:
    t = _STRIP_RE.sub("", (title or "").lower())
    return _NOISE_RE.sub("", t) or t


def similarity(a: str, b: str) -> float:
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    if len(na) >= 4 and len(nb) >= 4 and (na in nb or nb in na):
        return 0.95
    return SequenceMatcher(None, na, nb).ratio()


@dataclass
class DupMatch:
    decision: Decision
    target: str                 # "calendar" | "task"
    existing: dict              # Google 이벤트/태스크 원본
    score: float
    tasklist_id: str = ""       # task 일 때 목록
    title: str = ""
    when: str = ""
    link: str = ""


@dataclass
class DedupeResult:
    matches: list[DupMatch] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def any(self) -> bool:
        return bool(self.matches)


def _event_when(e: dict) -> str:
    s = e.get("start", {})
    v = s.get("dateTime") or s.get("date") or ""
    return v.replace("T", " ")[:16]


def _event_date(e: dict) -> date | None:
    s = e.get("start", {})
    v = s.get("dateTime") or s.get("date")
    if not v:
        return None
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00")).date() if "T" in v else date.fromisoformat(v)
    except ValueError:
        return None


def _task_due(t: dict) -> date | None:
    v = t.get("due")
    if not v:
        return None
    try:
        return date.fromisoformat(v[:10])
    except ValueError:
        return None


def find_duplicates(decisions: list[Decision], settings: cfg.ScheduleSettings, *,
                    calendar: CalendarClient | None, tasks: TasksClient | None,
                    resolve_tasklist=None) -> DedupeResult:
    """resolve_tasklist(decision) -> tasklist_id (Registrar 와 같은 규칙). None 이면 설정 기본."""
    res = DedupeResult()
    if not decisions:
        return res

    # ---- 캘린더: 필요한 기간을 한 번에 조회
    cal_decisions = [d for d in decisions if "calendar" in d.targets]
    events: list[dict] = []
    if cal_decisions and calendar is not None:
        lo = min(d.item.start for d in cal_decisions) - timedelta(days=1)
        hi = max((d.item.end or d.item.start) for d in cal_decisions) + timedelta(days=2)
        try:
            events = calendar.list_events(settings.calendar_id, lo, hi, max_results=250)
        except Exception as e:  # noqa: BLE001
            res.errors.append(f"캘린더 조회 실패: {e}")
    for d in cal_decisions:
        d_lo = d.item.start.date() - timedelta(days=1)
        d_hi = (d.item.end or d.item.start).date() + timedelta(days=1)
        best = None
        for e in events:
            ed = _event_date(e)
            if ed is None or not (d_lo <= ed <= d_hi):
                continue
            sc = similarity(d.item.title, e.get("summary", ""))
            if sc >= THRESHOLD and (best is None or sc > best[0]):
                best = (sc, e)
        if best:
            sc, e = best
            res.matches.append(DupMatch(d, "calendar", e, sc, title=e.get("summary", ""), when=_event_when(e),
                                        link=e.get("htmlLink", "")))

    # ---- 태스크: 목록별로 미완료 조회 (캐시)
    task_decisions = [d for d in decisions if "task" in d.targets]
    if task_decisions and tasks is not None:
        cache: dict[str, list[dict]] = {}
        for d in task_decisions:
            tid = (resolve_tasklist(d) if resolve_tasklist else "") or d.tasklist_id or settings.tasklist_id or "@default"
            if tid not in cache:
                try:
                    cache[tid] = tasks.list_open_tasks(tid)
                except Exception as e:  # noqa: BLE001
                    res.errors.append(f"태스크 목록 조회 실패: {e}")
                    cache[tid] = []
            best = None
            for t in cache[tid]:
                sc = similarity(d.item.title, t.get("title", ""))
                if sc < THRESHOLD:
                    continue
                due = _task_due(t)
                if due is not None and not d.item.undated and abs((due - d.item.start.date()).days) > 3:
                    continue
                if best is None or sc > best[0]:
                    best = (sc, t)
            if best:
                sc, t = best
                due = _task_due(t)
                res.matches.append(DupMatch(d, "task", t, sc, tasklist_id=tid, title=t.get("title", ""),
                                            when=due.isoformat() if due else "(마감 없음)", link=t.get("selfLink", "")))
    return res
