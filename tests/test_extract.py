import json
from datetime import date, datetime

import pytest

from src.extract import ExtractionError, Extractor
from src.extract.schema import RawItem, ScheduleItem, normalize, parse_date, parse_time
from src.llm.base import LLMProvider, LLMRequest, ModelInfo
from src.parsers import ParsedInput

REF = date(2026, 8, 28)  # 금요일


# ---------------------------------------------------------------- 파싱 유틸

@pytest.mark.parametrize("s,expected", [
    ("2026-09-03", date(2026, 9, 3)),
    ("2026.9.3", date(2026, 9, 3)),
    ("2026년 9월 3일", date(2026, 9, 3)),
    ("9/3", date(2026, 9, 3)),
    ("1/15", date(2027, 1, 15)),       # 기준일 이후 가장 가까운 미래
    ("8/10", date(2026, 8, 10)),       # 30일 이내 과거는 허용
    ("2026-02-30", None),
    (None, None),
    ("언젠가", None),
])
def test_parse_date(s, expected):
    assert parse_date(s, REF) == expected


@pytest.mark.parametrize("s,expected", [
    ("14:00", (14, 0)), ("9:05", (9, 5)), ("오후 2시", (14, 0)), ("오전 12시", (0, 0)),
    ("14시 30분", (14, 30)), ("null", None), (None, None), ("25:00", None),
])
def test_parse_time(s, expected):
    t = parse_time(s)
    if expected is None:
        assert t is None
    else:
        assert (t.hour, t.minute) == expected


# ---------------------------------------------------------------- normalize

def test_normalize_all_day_and_timed():
    a = normalize(RawItem(title="제출", date="2026-09-10", kind="task"), REF, "x.hwp")
    assert a.all_day and a.kind == "task" and a.start == datetime(2026, 9, 10) and a.source == "x.hwp"
    b = normalize(RawItem(title="회의", date="2026-09-03", time="14:00", end_time="16:00"), REF)
    assert not b.all_day and b.start == datetime(2026, 9, 3, 14) and b.end == datetime(2026, 9, 3, 16)
    assert b.describe_when() == "2026-09-03 14:00~16:00"


def test_normalize_range_and_bad_end():
    r = normalize(RawItem(title="연수", date="2026-09-01", end_date="2026-09-05"), REF)
    assert r.all_day and r.end == datetime(2026, 9, 5) and r.describe_when() == "2026-09-01 ~ 2026-09-05"
    bad = normalize(RawItem(title="x", date="2026-09-05", time="10:00", end_date="2026-09-01", end_time="09:00"), REF)
    assert bad.end is None


def test_normalize_no_date():
    assert normalize(RawItem(title="x"), REF) is None


# ---------------------------------------------------------------- Extractor (가짜 공급자)

class FakeProvider(LLMProvider):
    name = "fake"
    supports_vision_default = True

    def __init__(self, responses):
        super().__init__("fake-model")
        self.responses = list(responses)
        self.calls: list[LLMRequest] = []

    def list_models(self):
        return [ModelInfo("fake-model")]

    def complete(self, req):
        self.calls.append(req)
        return self.responses.pop(0)


def test_extract_basic():
    resp = json.dumps({"items": [
        {"title": "학교운영위원회", "date": "2026-09-03", "time": "14:00", "kind": "event", "location": "회의실", "confidence": 0.95},
        {"title": "신청서 제출", "date": "9/10", "time": None, "kind": "task"},
        {"title": "날짜없음", "date": None},
        {"title": "학교운영위원회", "date": "2026-09-03", "time": "14:00", "kind": "event"},  # 중복
    ]})
    p = FakeProvider([resp])
    r = Extractor(p).extract(ParsedInput(text="본문", source="공문.hwp"), REF)
    assert [i.title for i in r.items] == ["학교운영위원회", "신청서 제출"]
    assert r.items[1].all_day and r.items[1].start_date == date(2026, 9, 10) and r.items[1].kind == "task"
    assert r.items[0].source == "공문.hwp"
    assert any("제외" in w for w in r.warnings)
    assert "기준일: 2026-08-28 (금요일)" in p.calls[0].text and "본문" in p.calls[0].text


def test_extract_retries_on_bad_json_then_fails():
    p = FakeProvider(["not json", "still not json"])
    with pytest.raises(ExtractionError):
        Extractor(p).extract(ParsedInput(text="x"), REF)
    assert len(p.calls) == 2 and "올바른 JSON" in p.calls[1].text


def test_extract_repair_succeeds():
    p = FakeProvider(["garbage", '{"items":[{"title":"a","date":"2026-09-01"}]}'])
    r = Extractor(p).extract(ParsedInput(text="x"), REF)
    assert len(r.items) == 1


def test_extract_images_passed_and_list_response():
    p = FakeProvider(['[{"title":"이미지 일정","date":"2026-09-02","time":"오후 3시"}]'])
    r = Extractor(p).extract(ParsedInput(images=[b"png1", b"png2"]), REF)
    assert len(p.calls[0].images) == 2 and "이미지" in p.calls[0].text
    assert r.items[0].start == datetime(2026, 9, 2, 15)


def test_extract_long_text_truncated():
    p = FakeProvider(['{"items":[]}'])
    r = Extractor(p).extract(ParsedInput(text="x" * 50_000), REF)
    assert r.items == [] and any("길어" in w for w in r.warnings)
    assert len(p.calls[0].text) < 45_000
