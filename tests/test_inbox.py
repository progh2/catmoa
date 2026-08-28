from datetime import date

import pytest

from src.gsync.tasks import TasksClient
from src.sources.inbox import InboxNotFound, fetch_inbox_items
from tests.test_gsync_register import FakeService


def test_fetch_inbox_items():
    svc = FakeService()
    items, list_id = fetch_inbox_items(TasksClient(svc), "인박스")
    assert list_id == "L2"
    assert len(items) == 1
    it = items[0]
    assert it.kind == "inbox_task" and it.payload.startswith("금요일 가정통신문")
    assert it.origin_ref == "L2:t1" and it.source_label.startswith("인박스: ")
    assert it.reference_date == date.today()


def test_fetch_inbox_missing_list():
    with pytest.raises(InboxNotFound):
        fetch_inbox_items(TasksClient(FakeService()), "없는목록")
