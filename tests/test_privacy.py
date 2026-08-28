import json
from datetime import date

from src.extract import Extractor
from src.parsers import ParsedInput
from src.privacy import mask_text, restore_text
from src.privacy.masker import TOKEN_RE
from tests.test_extract import FakeProvider

REF = date(2026, 6, 8)


def test_mask_structured_and_names():
    text = ("담당: 김민수 (010-1234-5678, kim@school.kr) 문의. 주민번호 900101-1234568.\n"
            "2학년 3반 학생 명단 제출. 홍길동 선생님께 회신. 비밀번호: abcd1234 접속. "
            "주소: 서울특별시 관악구 봉천로 12 (2층)")
    r = mask_text(text, use_model=False)
    m = r.masked
    assert "010-1234-5678" not in m and "kim@school.kr" not in m and "900101-1234568" not in m
    assert mask_text("주민번호 900101-1234567", use_model=False).count == 0     # 체크섬 무효 → 주민번호 아님
    assert "김민수" not in m and "홍길동" not in m and "abcd1234" not in m and "봉천로" not in m
    assert "[전화1]" in m and "[이메일1]" in m and "[이름1]" in m and "[이름2]" in m and "[반1]" in m
    assert r.count >= 7 and "이름 2" in r.summary()
    # 복원
    assert restore_text("[이름1]에게 [전화1]로 연락", r.mapping) == "김민수에게 010-1234-5678로 연락"
    assert restore_text(None, r.mapping) is None
    assert restore_text("토큰 없음", r.mapping) == "토큰 없음"
    assert set(TOKEN_RE.findall(m)) >= {("전화", "1"), ("이름", "1")}


def test_same_value_same_token_and_context_gating():
    r = mask_text("김민수 선생님, 김민수 선생님께 010-1111-2222 로. 3교시 수업은 7-2 문제 풀이.", use_model=False)
    assert r.masked.count("[이름1]") == 2 and "[이름2]" not in r.masked
    assert "3교시" in r.masked and "7-2" in r.masked         # 교시/문제 맥락은 학급으로 보지 않음
    assert mask_text("", use_model=False).masked == "" and mask_text("일정 없는 평범한 문장", use_model=False).count == 0


def test_role_names_and_non_person_words():
    r = mask_text("체육 선생님과 2학년 선생님께 안내. 박지훈 부장님, 최유나 교감선생님이 참석.", use_model=False)
    assert "체육" in r.masked and "2학년" in r.masked                # 교과·학년은 이름이 아님
    assert "박지훈" not in r.masked and "최유나" not in r.masked


def test_roster_and_student_numbers():
    text = "학번\n이름\n전화번호\n20315\n박서연\n010-2222-3333\n"
    r = mask_text(text, use_model=False)
    assert "박서연" not in r.masked and "20315" not in r.masked and "[학번1]" in r.masked


def test_extractor_masks_prompt_but_keeps_source_and_restores():
    resp = json.dumps({"items": [{"title": "[이름1] 학생 상담", "date": "2026-06-10", "time": "14:00",
                                  "notes": "[전화1]로 연락", "location": "[이름2] 교실"}]})
    prov = FakeProvider([resp])
    text = "6/10 14:00 김민수 학생 상담. 연락처 010-1234-5678. 장소는 이서준 선생님 교실"
    r = Extractor(prov).extract(ParsedInput(text=text), REF, mask_pii=True)
    sent = prov.calls[0].text
    assert "김민수" not in sent and "010-1234-5678" not in sent and "[이름1]" in sent
    it = r.items[0]
    assert it.title == "김민수 학생 상담" and it.notes == "010-1234-5678로 연락" and it.location == "이서준 교실"
    assert it.source_text == text                       # 원문은 그대로
    assert any("🔒" in w for w in r.warnings)
    # 끄면 원문 그대로 전송
    prov2 = FakeProvider([json.dumps({"items": []})])
    Extractor(prov2).extract(ParsedInput(text=text), REF, mask_pii=False)
    assert "김민수" in prov2.calls[0].text


# ---------------------------------------------------------------- 설정 '개인정보' 탭 (#55)

def test_settings_privacy_tab_toggle_and_check(tmp_path, monkeypatch):
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from src import config as cfg
    from src.ui.settings_dialog import SettingsDialog

    monkeypatch.setenv("CATMOA_CONFIG_DIR", str(tmp_path))
    QApplication.instance() or QApplication([])
    c = cfg.Config()
    dlg = SettingsDialog(c, initial_tab="privacy")
    assert dlg.tabs.currentIndex() == SettingsDialog.TAB_INDEX["privacy"]
    assert dlg.tabs.tabText(dlg.tabs.currentIndex()) == "개인정보"
    assert dlg.mask_pii.isChecked()                       # 기본 켜짐

    # 예시 문장으로 확인 → 무엇이 가려졌는지 요약 + 되돌리기 검증
    dlg._pii_test()
    out = dlg.pii_output.toPlainText()
    assert "김민수" not in out and "010-1234-5678" not in out and "kim@school.kr" not in out
    assert "[이름1]" in out and "[전화1]" in out
    assert "곳을 가렸어요" in dlg.pii_summary.text() and "되돌리기 확인 ✅" in dlg.pii_summary.text()

    # 꺼도 확인 기능은 동작하되 "실제로는 원문이 전달된다"고 알려준다
    dlg.mask_pii.setChecked(False)
    dlg._pii_test()
    assert "꺼져 있어" in dlg.pii_summary.text()

    # 가릴 게 없는 문장 / 빈 문장
    dlg.pii_input.setPlainText("내일 회의는 3층에서 합니다.")
    dlg._pii_test()
    assert "찾지 못했어요" in dlg.pii_summary.text()
    dlg.pii_input.setPlainText("   ")
    dlg._pii_test()
    assert "넣어 주세요" in dlg.pii_summary.text()

    dlg._save()
    assert c.schedule.mask_pii is False                   # 끄기 설정이 저장된다
