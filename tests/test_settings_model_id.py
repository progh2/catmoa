"""설정 다이얼로그 모델 콤보 → 실제 모델 id 변환 (연결 테스트가 '(비전)' 태그를 모델명으로 보내던 버그 회귀 테스트)."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QComboBox

from src.llm.openai_ import OpenAIProvider
from src.ui.settings_dialog import SettingsDialog


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _dlg_model_id(app, items: list[tuple[str, str]], select: int | None = None, typed: str | None = None) -> str:
    combo = QComboBox()
    combo.setEditable(True)
    for text, data in items:
        combo.addItem(text, data)
    if select is not None:
        combo.setCurrentIndex(select)
    if typed is not None:
        combo.setEditText(typed)

    class _Stub:
        model = combo
    return SettingsDialog._model_id(_Stub())


def test_model_id_from_list_item_strips_vision_tag(app):
    items = [("gpt-4o (비전)", "gpt-4o"), ("gpt-4o-mini (비전)", "gpt-4o-mini")]
    assert _dlg_model_id(app, items, select=1) == "gpt-4o-mini"


def test_model_id_typed_value_kept(app):
    assert _dlg_model_id(app, [("gpt-4o (비전)", "gpt-4o")], typed="gpt-4.1-nano") == "gpt-4.1-nano"


def test_model_id_typed_with_tag_stripped(app):
    assert _dlg_model_id(app, [], typed="gpt-4o (비전)") == "gpt-4o"


class _M:
    def __init__(self, i): self.id = i


class _FakeModels:
    def __init__(self, ids): self._ids = ids
    def list(self): return [_M(i) for i in self._ids]


class _FakeClient:
    def __init__(self, ids): self.models = _FakeModels(ids)


def test_openai_list_excludes_responses_only_models():
    ids = ["gpt-4o", "o1-pro", "o3-pro", "gpt-5-pro", "gpt-5-codex", "codex-mini-latest", "o3-deep-research",
           "gpt-4o-mini", "text-embedding-3-small", "gpt-5", "o3"]
    p = OpenAIProvider(api_key="", model="gpt-4o", client=_FakeClient(ids))
    got = [m.id for m in p.list_models()]
    assert got == ["gpt-4o", "gpt-4o-mini", "gpt-5", "o3"]
