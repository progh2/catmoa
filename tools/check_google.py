"""Google 연동 실검증 스크립트 (개발용).

.env 에 CATMOA_GOOGLE_CLIENT_ID / CATMOA_GOOGLE_CLIENT_SECRET 를 넣고:
    python tools/check_google.py            # 로그인 상태 확인 + 목록 조회
    python tools/check_google.py --login    # 브라우저 로그인
    python tools/check_google.py --write    # 테스트 이벤트/태스크 생성 후 즉시 삭제
    python tools/check_google.py --logout
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.extract.schema import ScheduleItem  # noqa: E402
from src.gsync.auth import GoogleAuth, GoogleAuthError  # noqa: E402
from src.gsync.calendar import CalendarClient  # noqa: E402
from src.gsync.tasks import TasksClient  # noqa: E402


def main() -> int:
    g = GoogleAuth()
    args = set(sys.argv[1:])
    if "--logout" in args:
        g.logout()
        print("로그아웃 완료")
        return 0
    if "--login" in args or not g.is_logged_in():
        try:
            print("브라우저에서 로그인하세요…")
            print("로그인:", g.login())
        except GoogleAuthError as e:
            print("❌", e)
            return 1
    print("계정:", g.email() or "(이메일 미확인)")
    cals = g.list_calendars()
    lists = g.list_tasklists()
    print(f"캘린더 {len(cals)}개:", [n for _, n in cals][:8])
    print(f"태스크 목록 {len(lists)}개:", [n for _, n in lists][:8])

    if "--write" in args:
        cal = CalendarClient(g.calendar_service())
        tasks = TasksClient(g.tasks_service())
        start = datetime.now().replace(second=0, microsecond=0) + timedelta(days=1)
        item = ScheduleItem(title="catmoa 테스트 이벤트", start=start, end=start + timedelta(hours=1),
                            kind="event", location="테스트", notes="자동 삭제됨", source="check_google.py")
        ev = cal.create_event(item, "primary", 10)
        print("이벤트 생성:", ev.get("htmlLink"))
        g.calendar_service().events().delete(calendarId="primary", eventId=ev["id"]).execute()
        print("이벤트 삭제 완료")
        t = tasks.create_task(item.model_copy(update={"kind": "task", "title": "catmoa 테스트 태스크"}))
        print("태스크 생성:", t.get("id"))
        g.tasks_service().tasks().delete(tasklist="@default", task=t["id"]).execute()
        print("태스크 삭제 완료")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
