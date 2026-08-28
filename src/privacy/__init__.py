"""LLM 전송 전 개인정보 마스킹 (로컬 처리, 네트워크 없음).

- 규칙 기반(내장): 전화·이메일·주민번호·문서/계정 ID·IP·주소·생년월일·비밀값·학번/반·명단·직함 앞 이름
- 모델(선택): `schift-ko-pii` 패키지 + 로컬 모델 폴더가 있으면 문맥 기반 인명/주소 탐지를 추가
마스킹은 되돌릴 수 있게 번호 토큰([이름1], [전화2] …)을 쓰고, LLM 결과의 제목·메모에 남은 토큰은 원문으로 복원한다.
사용자 제공 coolmsg_v6_pipeline(rules.py / run_masking.py)을 참고해 이식.
"""
from src.privacy.masker import MaskResult, mask_text, model_available, restore_text

__all__ = ["MaskResult", "mask_text", "restore_text", "model_available"]
