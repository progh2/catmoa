import json
from datetime import date, datetime

from src.extract import Extractor
from src.extract.schema import ScheduleItem
from src.gsync.calendar import event_body
from src.gsync.tasks import task_body
from src.parsers import ParsedInput
from tests.test_extract import FakeProvider

REF = date(2026, 6, 8)
RESP = json.dumps({"items": [{"title": "회의", "date": "2026-06-10", "time": "14:00"},
                             {"title": "제출", "date": "2026-06-12", "kind": "task"}]})


def test_extractor_attaches_source_excerpt():
    r = Extractor(FakeProvider([RESP])).extract(ParsedInput(text="  6/10 14:00 회의, 6/12 제출  "), REF)
    assert all(i.source_text == "6/10 14:00 회의, 6/12 제출" for i in r.items)
    long = "가" * 2000
    r2 = Extractor(FakeProvider([RESP])).extract(ParsedInput(text=long), REF, source_chars=100)
    assert r2.items[0].source_text.startswith("가" * 100) and r2.items[0].source_text.endswith("…(이하 생략)")
    r3 = Extractor(FakeProvider([RESP])).extract(ParsedInput(text=long), REF, source_chars=0)
    assert r3.items[0].source_text == ""
    r4 = Extractor(FakeProvider([RESP])).extract(ParsedInput(images=[b"png"]), REF)
    assert r4.items[0].source_text == "(이미지 1장 입력)"


def test_bodies_include_source_section():
    it = ScheduleItem(title="회의", start=datetime(2026, 6, 10, 14), kind="event", notes="근거", source="쿨메신저: 김",
                      source_text="원문 본문입니다.\n둘째 줄")
    d = event_body(it, 10)["description"]
    assert "근거" in d and "─── 원문 ───" in d and d.endswith("원문 본문입니다.\n둘째 줄")
    assert d.index("catmoa 🐱 로 등록") < d.index("─── 원문 ───")
    n = task_body(it.model_copy(update={"kind": "task"}))["notes"]
    assert n.endswith("원문 본문입니다.\n둘째 줄") and "─── 원문 ───" in n and n.index("출처") < n.index("─── 원문")
    # 원문 없으면 구역도 없음
    plain = ScheduleItem(title="x", start=datetime(2026, 6, 10), all_day=True, kind="task")
    assert "원문" not in task_body(plain).get("notes", "") and "원문" not in event_body(plain, None)["description"]
