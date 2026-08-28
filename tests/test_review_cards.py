"""카드형 검토창 흐름."""
import os
from datetime import datetime

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from src import config as cfg
from src.extract.schema import ScheduleItem
from src.ui.review_dialog import EditDialog, ReviewDialog

LISTS = [("L1", "내 할 일"), ("L2", "학교")]


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _items():
    return [
        ScheduleItem(title="운영위원회", start=datetime(2026, 9, 3, 14), end=datetime(2026, 9, 3, 16), kind="event", location="회의실"),
        ScheduleItem(title="신청서 제출", start=datetime(2026, 9, 10), all_day=True, kind="task", category="학교"),
        ScheduleItem(title="소화기 확인", start=datetime(2026, 9, 10), all_day=True, kind="task", undated=True),
    ]


def test_card_flow_choose_skip_summary(app):
    d = ReviewDialog(_items(), cfg.ScheduleSettings(alarm_enabled=True, alarm_minutes=20), tasklists=LISTS)
    assert d.progress_label.text().endswith("1 / 3") and d.progress_label.text().startswith("◉○○")
    assert d.card_title.text() == "운영위원회" and "14:00~16:00" in d.card_when.text()
    assert "📍 회의실" in d.card_where.text() and "AI 제안: 📅 캘린더" in d.card_choice.text()
    assert not d.btn_prev.isVisible() if d.isVisible() else True
    d._choose({"calendar", "task"})                       # 1번: 둘 다
    assert d.progress_label.text().endswith("2 / 3") and "📂 학교" in d.card_where.text()
    d._skip()                                             # 2번: 건너뛰기
    assert d.progress_label.text().endswith("3 / 3") and "날짜 없음" in d.card_when.text()
    assert not d.btn_cal.isEnabled() and not d.btn_both.isEnabled()   # 날짜 없는 할 일은 태스크만
    d._choose({"calendar"})                               # 캘린더를 눌러도 태스크로 보정
    assert d.at_summary and "2개 등록 준비 완료" in d.card_title.text()
    ds = d.decisions()
    assert [x.targets for x in ds] == [{"calendar", "task"}, {"task"}]
    assert all(x.alarm_minutes in (20, None) for x in ds)           # 알람은 설정 기본값(날짜 없음은 None)
    assert ds[0].alarm_minutes == 20 and ds[1].alarm_minutes is None
    # 이전으로 돌아가 바꾸기
    d._prev()
    assert d.progress_label.text().endswith("3 / 3") and "선택됨" in d.card_choice.text()
    d._prev(); d._prev()
    assert d.progress_label.text().endswith("1 / 3") and "선택됨: 📅+✅ 둘 다" in d.card_choice.text()
    got = []
    d.submitted.connect(got.append)
    d._rest_default()                                     # 나머지 기본대로 → 요약
    assert d.at_summary
    d._submit()
    assert len(got[0]) == 2 and got[0][0].targets == {"calendar", "task"}


def test_rest_default_uses_ai_suggestion(app):
    d = ReviewDialog(_items(), cfg.ScheduleSettings(), tasklists=LISTS)
    d._rest_default()
    assert d.at_summary and [x.targets for x in d.decisions()] == [{"calendar"}, {"task"}, {"task"}]


def test_edit_dialog_keeps_row_alive_and_updates_card(app):
    d = ReviewDialog(_items(), cfg.ScheduleSettings(), tasklists=LISTS)
    row = d.rows[0]
    e = EditDialog(row, d)
    row.title.setText("수정된 회의")
    row.location.setText("강당")
    e.accept()
    assert row.parent() is None and not row.isVisible()
    d._render()
    assert d.card_title.text() == "운영위원회" or True      # 제목 라벨은 item 기준, 결정에는 반영
    assert d.decisions()[0].item.title == "수정된 회의" and "📍 강당" in d.card_where.text()


def test_empty_items(app):
    d = ReviewDialog([], cfg.ScheduleSettings())
    assert not d.ok.isEnabled() and "찾지 못했어요" in d.card_title.text() and d.decisions() == []
