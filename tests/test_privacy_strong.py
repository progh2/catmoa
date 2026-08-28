"""강력한 마스킹(내려받는 ONNX 모델) — 설치/삭제/폴백 (#60).

모델 파일(약 300MB)은 테스트에 넣지 않는다. 내려받기는 가짜 응답으로, 추론 경로는
가짜 Detector 로 확인하고, 모델이 없을 때 규칙만으로 조용히 동작하는지를 본다.
"""
import hashlib
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import httpx
import pytest

from src.privacy import mask_text, strong

BODIES = {"model.onnx": b"onnx-bytes" * 100, "tokenizer.json": b'{"tok": 1}', "labels.json": b'{"id2label": {}}'}


def _manifest():
    return {"model_id": "test", "files": {n: {"size": len(b), "sha256": hashlib.sha256(b).hexdigest()}
                                          for n, b in BODIES.items()}}


def _transport(manifest=True, corrupt=False):
    def handler(request: httpx.Request) -> httpx.Response:
        name = request.url.path.rsplit("/", 1)[-1]
        if name == "manifest.json":
            return httpx.Response(200 if manifest else 404, json=_manifest() if manifest else {})
        if name in BODIES:
            body = b"corrupted!" if corrupt else BODIES[name]
            return httpx.Response(200, content=body)
        return httpx.Response(404)

    return httpx.MockTransport(handler)


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("CATMOA_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("CATMOA_PII_MODEL", str(tmp_path / "pii_model"))
    strong.Detector.reset()
    yield
    strong.Detector.reset()


def test_not_installed_falls_back_to_rules_quietly():
    assert not strong.is_installed()
    assert strong.spans("담임 김민수 선생님") == [] and not strong.active()
    r = mask_text("담임 김민수 선생님께 010-1234-5678", strong=True)
    assert "김민수" not in r.masked and "[전화1]" in r.masked and r.used_model is False


def test_download_installs_and_removes():
    seen = []
    root = strong.download(progress=lambda d, t: seen.append((d, t)), transport=_transport())
    assert root == strong.model_root() and strong.is_installed()
    assert strong.installed_size() == sum(len(b) for b in BODIES.values())
    assert seen and seen[-1][0] == seen[-1][1]                  # 마지막에 100%
    assert (root / "model.onnx").read_bytes() == BODIES["model.onnx"]

    strong.remove()
    assert not strong.is_installed() and not root.exists()


def test_download_rejects_corrupted_file():
    with pytest.raises(RuntimeError, match="손상"):
        strong.download(transport=_transport(corrupt=True))
    assert not strong.is_installed()                            # 실패하면 아무것도 남기지 않는다
    assert not strong.model_root().with_name("pii_model.part").exists()


def test_download_works_without_manifest():
    strong.download(transport=_transport(manifest=False))
    assert strong.is_installed()


def test_download_can_be_cancelled():
    with pytest.raises(RuntimeError, match="취소"):
        strong.download(should_stop=lambda: True, transport=_transport())
    assert not strong.is_installed()


def test_expected_size_reads_manifest_and_falls_back():
    assert strong.expected_size(transport=_transport()) == sum(len(b) for b in BODIES.values())
    assert strong.expected_size(transport=_transport(manifest=False)) == 150_000_000


def test_spans_map_labels_and_protect_schedule_dates(monkeypatch):
    """모델이 찾은 것 중 일정 날짜는 절대 가리지 않는다 (가리면 앱이 일을 못 한다)."""
    text = "김민수 선생님, 9월 3일 14:00 회의입니다. 생년월일은 1985년 3월 12일."

    class FakeDet:
        def detect(self, t):
            return [strong._Span("private_person", 0, 3, 0.99),
                    strong._Span("private_date", t.index("9월 3일"), t.index("9월 3일") + 6, 0.9),
                    strong._Span("private_date", t.index("1985년"), t.index("1985년") + 12, 0.9)]

    monkeypatch.setattr(strong.Detector, "get", classmethod(lambda cls: FakeDet()))
    got = strong.spans(text)
    labels = [(s["label"], text[s["start"]:s["end"]]) for s in got]
    assert ("person", "김민수") in labels
    assert not any(v.startswith("9월") for _, v in labels)        # 일정 날짜는 통과
    assert any(l == "birth" for l, _ in labels)                   # 생년월일 맥락은 가림
    assert all(s["rule"] == "strong_model" and s["prio"] == 2 for s in got)


def test_trim_strips_josa_and_brackets():
    t = "학생 박서연(학번), 담당자 김민수님께"
    s, e = strong._trim(t, "private_person", t.index("박서연"), t.index("박서연") + 4)   # '박서연('
    assert t[s:e] == "박서연"
    s, e = strong._trim(t, "private_person", t.index("김민수"), t.index("김민수") + 5)   # '김민수님께'
    assert t[s:e] == "김민수"


def test_status_line_reports_state():
    assert "아직" in strong.status_line()
    strong.download(transport=_transport())
    assert "설치됨" in strong.status_line()


def test_settings_tab_shows_size_warning_and_buttons(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication

    from src import config as cfg
    from src.ui.settings_dialog import SettingsDialog

    QApplication.instance() or QApplication([])
    dlg = SettingsDialog(cfg.Config(), initial_tab="privacy")
    assert "300MB" in dlg.strong_warn.text() and "주의" in dlg.strong_warn.text()
    assert dlg.btn_strong_get.isEnabled() and not dlg.btn_strong_del.isEnabled()
    assert not dlg.mask_strong.isChecked() and not dlg.mask_strong.isEnabled()   # 없으면 켤 수 없다

    strong.download(transport=_transport())
    dlg2 = SettingsDialog(cfg.Config(), initial_tab="privacy")
    assert "설치됨" in dlg2.strong_warn.text()
    assert dlg2.btn_strong_del.isEnabled() and not dlg2.btn_strong_get.isEnabled()
    assert dlg2.mask_strong.isEnabled()
    dlg2.mask_strong.setChecked(True)
    dlg2._save()
    assert dlg2.config.schedule.mask_strong is True


def test_config_roundtrip_keeps_flag(tmp_path, monkeypatch):
    from src import config as cfg

    c = cfg.Config()
    c.schedule.mask_strong = True
    c.save()
    assert cfg.Config.load().schedule.mask_strong is True
