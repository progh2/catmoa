"""사용자 분류 규칙 / 카테고리가 프롬프트와 파이프라인에 반영되는지."""
import json
from datetime import date

from src.extract import Extractor
from src.extract.prompts import user_prompt
from src.parsers import ParsedInput
from tests.test_extract import FakeProvider

REF = date(2026, 8, 28)


def test_user_prompt_sections():
    p = user_prompt("본문", REF, kind_rules="연수는 캘린더", category_rules="공문은 '학교'", categories=["학교", "담임"])
    assert "사용자 분류 규칙" in p and "연수는 캘린더" in p
    assert '"학교", "담임"' in p and "카테고리 선택 규칙" in p and "공문은 '학교'" in p
    plain = user_prompt("본문", REF)
    assert "사용자 분류 규칙" not in plain and "카테고리" not in plain   # 규칙 없으면 입력 블록만
    p2 = user_prompt("본문", REF, category_rules="규칙만")
    assert "태스크 카테고리 규칙" in p2 and "다음 목록 중" not in p2


def test_calendar_hint_in_prompt():
    from src.extract.prompts import calendar_hint
    h = calendar_hint(date(2026, 6, 8))            # 월요일
    assert h.startswith("날짜 참고") and "이번 주: 06/08(월)" in h and "06/14(일)" in h
    assert "다음 주: 06/15(월)" in h and "06/18(목)" in h and "다다음 주: 06/22(월)" in h
    assert "06/18(목)" in user_prompt("x", date(2026, 6, 8))


def test_extractor_drop_before():
    resp = json.dumps({"items": [
        {"title": "지난 제출", "date": "2026-06-03", "kind": "task"},
        {"title": "회의", "date": "2026-06-18", "time": "14:00"},
    ]})
    r = Extractor(FakeProvider([resp])).extract(ParsedInput(text="x"), date(2026, 6, 8), drop_before=date(2026, 6, 8))
    assert [i.title for i in r.items] == ["회의"] and any("지나간 항목 1개" in w for w in r.warnings)
    r2 = Extractor(FakeProvider([resp])).extract(ParsedInput(text="x"), date(2026, 6, 8))
    assert len(r2.items) == 2


def test_extractor_passes_options_and_category():
    resp = json.dumps({"items": [{"title": "신청서 제출", "date": "2026-09-10", "kind": "task", "category": "학교"}]})
    prov = FakeProvider([resp])
    r = Extractor(prov).extract(ParsedInput(text="x"), REF, kind_rules="R1", category_rules="R2", categories=["학교"])
    assert r.items[0].category == "학교"
    assert "R1" in prov.calls[0].text and "R2" in prov.calls[0].text and '"학교"' in prov.calls[0].text
