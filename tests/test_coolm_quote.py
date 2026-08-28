"""쿨메신저 답장에 쌓인 이전 대화 분리."""
from datetime import datetime

import pytest

from src.sources.coolm import Message, split_recent
from src.sources.coolm_watcher import message_to_item


@pytest.mark.parametrize("body", [
    "내일 3시 회의로 확정합니다.\n\n----- 원본 메시지 -----\n보낸 사람: 김선생\n지난주 회의 결과 공유드립니다. 6/1 10시에 모였습니다.",
    "내일 3시 회의로 확정합니다.\n\n-----Original Message-----\nFrom: kim\nSent: 2026-06-01\n지난주 6/1 10시 회의",
    "내일 3시 회의로 확정합니다.\n─────────────────\n지난주 6/1 10시 회의",
    "내일 3시 회의로 확정합니다.\n\n> 지난주 6/1 10시 회의\n> 자료는 첨부 참고\n> 감사합니다",
    "내일 3시 회의로 확정합니다.\n\n보낸 사람: 김선생\n보낸 날짜: 2026-06-01 10:00\n제목: 회의\n지난주 6/1 10시 회의",
    "내일 3시 회의로 확정합니다.\n2026-06-01 김선생님이 작성:\n지난주 6/1 10시 회의",
])
def test_split_recent_formats(body):
    recent, older = split_recent(body)
    assert recent == "내일 3시 회의로 확정합니다."
    assert "6/1 10시" in older and not older.startswith(">")


def test_split_recent_no_quote_and_edge_cases():
    assert split_recent("내일 3시 회의") == ("내일 3시 회의", "")
    assert split_recent("") == ("", "")
    # 첫 줄이 헤더처럼 보여도(작성자가 '제목:' 으로 시작) 인용으로 자르지 않는다
    r, o = split_recent("제목: 회의 안내\n내일 3시입니다.")
    assert o == "" and "내일" in r
    # 본문 중간의 짧은 '-' 는 구분선이 아님
    assert split_recent("내일 3시 - 회의실\n준비물 지참")[1] == ""


def test_to_text_sections_and_truncation():
    body = "최근: 금요일까지 제출\n\n----- 원본 메시지 -----\n" + "옛날 대화 " * 500
    m = Message(key=1, sender="김", received=datetime(2026, 6, 8, 9), title="회신", body=body)
    t = m.to_text(history_chars=100)
    assert "[최근 내용]" in t and "금요일까지 제출" in t
    assert "[이전 대화" in t and "…(이하 생략)" in t
    assert t.index("[최근 내용]") < t.index("[이전 대화")
    assert len(t.split("[이전 대화")[1]) < 200
    t0 = m.to_text(history_chars=0)
    assert "[이전 대화" not in t0 and "옛날 대화" not in t0 and "[최근 내용]" in t0
    plain = Message(key=2, sender="김", received=datetime(2026, 6, 8, 9), title="", body="내일 3시 회의").to_text()
    assert "[최근 내용]" not in plain and plain.endswith("내일 3시 회의")


def test_message_to_item_uses_history_setting():
    body = "내일 3시 회의\n\n> 지난주 이야기\n> 더 지난 이야기"
    m = Message(key=3, sender="김", received=datetime(2026, 6, 8, 9), title="", body=body)
    assert "지난주" in message_to_item(m, 500).payload
    assert "지난주" not in message_to_item(m, 0).payload
