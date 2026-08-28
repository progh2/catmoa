"""Google Tasks 생성/조회/완료."""
from __future__ import annotations

from src.extract.schema import ScheduleItem

DEFAULT_LIST = "@default"


def task_body(item: ScheduleItem) -> dict:
    notes_parts = []
    if not item.all_day:
        notes_parts.append(f"시각: {item.start.strftime('%H:%M')}")   # Tasks API는 due 의 시간을 무시한다
    if item.location:
        notes_parts.append(f"장소: {item.location}")
    if item.notes:
        notes_parts.append(item.notes)
    if item.source:
        notes_parts.append(f"출처: {item.source}")
    body: dict = {
        "title": item.title,
        # RFC3339. 날짜만 의미 있음 (시간 부분은 API가 버린다)
        "due": item.start.date().isoformat() + "T00:00:00.000Z",
    }
    if notes_parts:
        body["notes"] = "\n".join(notes_parts)
    return body


class TasksClient:
    def __init__(self, service):
        self.svc = service

    def create_task(self, item: ScheduleItem, tasklist_id: str = "") -> dict:
        return self.svc.tasks().insert(tasklist=tasklist_id or DEFAULT_LIST, body=task_body(item)).execute()

    def find_tasklist(self, name: str) -> tuple[str, str] | None:
        """이름(대소문자·공백 무시)으로 목록 찾기 → (id, title)."""
        key = "".join(name.split()).lower()
        page = None
        while True:
            resp = self.svc.tasklists().list(maxResults=100, pageToken=page).execute()
            for t in resp.get("items", []):
                if "".join(t.get("title", "").split()).lower() == key:
                    return t["id"], t.get("title", "")
            page = resp.get("nextPageToken")
            if not page:
                return None

    def create_tasklist(self, name: str) -> tuple[str, str]:
        t = self.svc.tasklists().insert(body={"title": name}).execute()
        return t["id"], t.get("title", name)

    def list_open_tasks(self, tasklist_id: str) -> list[dict]:
        out: list[dict] = []
        page = None
        while True:
            resp = self.svc.tasks().list(tasklist=tasklist_id, showCompleted=False, showHidden=False,
                                         maxResults=100, pageToken=page).execute()
            for t in resp.get("items", []):
                if t.get("status") == "completed" or not (t.get("title") or "").strip():
                    continue
                out.append(t)
            page = resp.get("nextPageToken")
            if not page:
                break
        return out

    def update_task(self, tasklist_id: str, task_id: str, item: ScheduleItem) -> dict:
        """기존 태스크의 마감·메모를 새 항목으로 갱신 (제목은 기존 유지)."""
        body = task_body(item)
        patch = {"due": body["due"]}
        if body.get("notes"):
            patch["notes"] = body["notes"]
        return self.svc.tasks().patch(tasklist=tasklist_id or DEFAULT_LIST, task=task_id, body=patch).execute()

    def complete_task(self, tasklist_id: str, task_id: str) -> dict:
        return self.svc.tasks().patch(tasklist=tasklist_id, task=task_id, body={"status": "completed"}).execute()
