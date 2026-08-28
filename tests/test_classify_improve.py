"""classifi_harness 반영: 쿨메신저 실제 인용 구분자, 역할 기반 scope, 날짜 없는 할 일, 토스트 문구."""
import json
import os
from datetime import date, datetime

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from src import config as cfg
from src.extract import Extractor
from src.extract.prompts import SYSTEM_PROMPT, user_prompt
from src.extract.schema import RawItem, normalize
from src.gsync.tasks import task_body
from src.parsers import ParsedInput
from src.sources.coolm import split_recent
from tests.test_extract import FakeProvider

REF = date(2026, 6, 8)


# ---------------------------------------------------------------- 쿨메신저 인용 구분자

@pytest.mark.parametrize("body", [
    "내일 3시 회의로 확정합니다.\n김선생님이 보낸글 >>\n지난주 6/1 10시 회의",
    "내일 3시 회의로 확정합니다.\n\n[교무부] 홍길동 님이 보낸 글 >>\n지난주 6/1 10시 회의",
    "내일 3시 회의로 확정합니다.\n보낸 메시지 전달 >>\n지난주 6/1 10시 회의",
    "내일 3시 회의로 확정합니다.\n메시지 전달 >>\n지난주 6/1 10시 회의",
])
def test_coolm_markers(body):
    recent, older = split_recent(body)
    assert recent == "내일 3시 회의로 확정합니다." and "6/1 10시" in older


def test_coolm_marker_on_first_line_means_forward_only():
    recent, older = split_recent("홍길동님이 보낸글 >>\n6/12 14:00 회의")
    assert recent == "" and "6/12" in older


# ---------------------------------------------------------------- 날짜 없는 할 일

def test_normalize_undated_task_kept_event_dropped():
    t = normalize(RawItem(title="교실 환경 정리", kind="task"), REF)
    assert t is not None and t.undated and t.kind == "task" and t.describe_when() == "날짜 없음"
    assert normalize(RawItem(title="회의", kind="event"), REF) is None


def test_task_body_undated_has_no_due():
    t = normalize(RawItem(title="교실 정리", kind="task"), REF)
    b = task_body(t)
    assert "due" not in b and b["title"] == "교실 정리"


def test_extractor_undated_and_scope():
    resp = json.dumps({"scope": "irrelevant", "scope_reason": "3학년 담임 대상", "items": [
        {"title": "3학년 진로캠프 인솔", "date": "2026-06-20", "kind": "event"},
        {"title": "명렬표 제출", "date": None, "kind": "task"},
    ]})
    # 역할이 없으면 scope 무시
    r = Extractor(FakeProvider([resp])).extract(ParsedInput(text="x"), REF)
    assert [i.title for i in r.items] == ["3학년 진로캠프 인솔", "명렬표 제출"] and r.items[1].undated and r.scope == "relevant"
    # 역할이 있고 irrelevant → 항목 비움 + 경고
    p = FakeProvider([resp])
    r2 = Extractor(p).extract(ParsedInput(text="x"), REF, persona="2학년 담임", skip_irrelevant=True)
    assert r2.items == [] and r2.scope == "irrelevant" and "3학년 담임 대상" in r2.warnings[-1]
    assert "사용자 역할" in p.calls[0].text and "2학년 담임" in p.calls[0].text
    # skip 끄면 유지 + ambiguous 는 경고만
    r3 = Extractor(FakeProvider([resp])).extract(ParsedInput(text="x"), REF, persona="2학년 담임", skip_irrelevant=False)
    assert len(r3.items) == 2
    amb = resp.replace("irrelevant", "ambiguous")
    r4 = Extractor(FakeProvider([amb])).extract(ParsedInput(text="x"), REF, persona="2학년 담임")
    assert len(r4.items) == 2 and any("불확실" in w for w in r4.warnings)


def test_drop_before_keeps_undated():
    resp = json.dumps({"items": [{"title": "정리", "date": None, "kind": "task"}, {"title": "옛날", "date": "2026-06-01", "kind": "task"}]})
    r = Extractor(FakeProvider([resp])).extract(ParsedInput(text="x"), REF, drop_before=REF)
    assert [i.title for i in r.items] == ["정리"]


def test_prompt_mentions_scope_and_actionable():
    assert '"scope"' in SYSTEM_PROMPT and "행동 문장" in SYSTEM_PROMPT and "[이름]" in SYSTEM_PROMPT
    assert "사용자 역할" not in user_prompt("x", REF)


# ---------------------------------------------------------------- 검토창 날짜 없음

def test_review_row_undated(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication
    from src.extract.schema import ScheduleItem
    from src.ui.review_dialog import ReviewDialog
    QApplication.instance() or QApplication([])
    it = ScheduleItem(title="교실 정리", start=datetime(2026, 6, 8), all_day=True, kind="task", undated=True)
    d = ReviewDialog([it], cfg.ScheduleSettings(default_target="both"), tasklists=[("L1", "학교")])
    r = d.rows[0]
    assert r.no_date.isChecked() and not r.cal.isEnabled() and not r.cal.isChecked() and r.task.isChecked()
    dec = d.decisions()[0]
    assert dec.targets == {"task"} and dec.item.undated and dec.alarm_minutes is None
    r.no_date.setChecked(False)                     # 날짜를 붙이면 캘린더도 가능
    assert r.cal.isEnabled()
    r.cal.setChecked(True)
    dec2 = d.decisions()[0]
    assert dec2.targets == {"calendar", "task"} and not dec2.item.undated
    d.close()


# ---------------------------------------------------------------- 일정 없음 안내 문구

def test_no_items_message():
    from src.extract.extractor import ExtractionResult
    from src.pipeline.items import InputItem
    from src.ui.main_window import _no_items_message
    assert _no_items_message(InputItem("text", "memo", source_label="클립보드 텍스트"), ExtractionResult([])) == "붙여넣은 텍스트에 일정이 없네요"
    m = _no_items_message(InputItem("coolm", "x", source_label="쿨메신저: 김선생"), ExtractionResult([], scope="irrelevant", scope_reason="3학년 대상"))
    assert m.startswith("쿨메신저 쪽지(김선생)") and "무관" in m and "3학년 대상" in m
    m2 = _no_items_message(InputItem("file", "/a/공문.hwp"), ExtractionResult([], warnings=["06/08 이전의 지나간 항목 2개를 제외했습니다: x"]))
    assert m2 == "공문.hwp에는 이미 지난 일정만 있네요"
