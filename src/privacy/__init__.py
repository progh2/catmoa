"""LLM 전송 전 개인정보 마스킹 (로컬 처리, 네트워크 없음).

- 규칙 기반(내장): 전화·이메일·주민번호·문서/계정 ID·IP·주소·생년월일·비밀값·학번/반·명단·직함 앞뒤 이름
- 강력한 마스킹(선택, `strong`): 설정에서 켜면 korean-pii-e5-base(ONNX int8, 약 300MB)를 내려받아
  문맥형 인명·주소까지 잡는다. onnxruntime 으로 돌리며 전부 PC 안에서 처리한다.
- 예전 경로(`masker._model_spans`): `schift-ko-pii` 패키지 + 로컬 모델 폴더가 있으면 함께 사용
마스킹은 되돌릴 수 있게 번호 토큰([이름1], [전화2] …)을 쓰고, LLM 결과의 제목·메모에 남은 토큰은 원문으로 복원한다.
"""
from src.privacy import strong
from src.privacy.masker import MaskResult, mask_text, model_available, restore_text

__all__ = ["MaskResult", "mask_text", "restore_text", "model_available", "strong"]
