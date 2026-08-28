"""Google Tasks 인박스 가져오기: 설정된 목록의 미완료 태스크 → InputItem 목록."""
from __future__ import annotations

from datetime import date, datetime

from src.gsync.tasks import TasksClient
from src.pipeline.items import InputItem


class InboxNotFound(Exception):
    pass


def fetch_inbox_items(tasks: TasksClient, list_name: str) -> tuple[list[InputItem], str]:
    """(items, tasklist_id). 목록이 없으면 InboxNotFound."""
    found = tasks.find_tasklist(list_name)
    if not found:
        raise InboxNotFound(f"Google Tasks에 '{list_name}' 목록이 없습니다. 휴대폰/웹에서 목록을 만들거나 설정에서 이름을 바꾸세요.")
    list_id, _ = found
    items: list[InputItem] = []
    for t in tasks.list_open_tasks(list_id):
        title = (t.get("title") or "").strip()
        notes = (t.get("notes") or "").strip()
        text = title if not notes else f"{title}\n{notes}"
        if t.get("due"):
            text += f"\n(마감으로 적어둔 날짜: {t['due'][:10]})"
        items.append(InputItem(
            kind="inbox_task",
            payload=text,
            source_label=f"인박스: {title[:30]}",
            reference_date=_updated_date(t) or date.today(),
            origin_ref=f"{list_id}:{t['id']}",
        ))
    return items, list_id


def _updated_date(t: dict) -> date | None:
    """태스크를 적은 날(updated)을 상대 날짜 기준일로 쓴다 — '내일'은 적은 날 기준이어야 하므로."""
    s = t.get("updated")
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone().date()
    except ValueError:
        return None
