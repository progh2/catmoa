# catmoa — 프로젝트 지침

교사 해커톤 프로젝트. 흩어진 일정 자료(hwp/hwpx/pdf/이미지/텍스트/쿨메신저/Tasks 인박스)를
고양이 위젯에 던지면 LLM이 일정을 추출해 Google Calendar/Tasks에 넣는 3-OS 데스크톱 앱.

## 개발 규칙
- `/sw-dev` 워크플로우: 이슈 단위 구현 → 커밋 `<type>: 설명 (closes #N)` → `gh issue close`
- GUI는 PySide6. 패키지명 `src/pipeline`(queue 아님), `src/gsync`(google 아님) — 네임스페이스 충돌 회피
- 파서는 순수 Python wheel만 (외부 바이너리 금지) — 3-OS PyInstaller 빌드 때문
- 비밀값: GitHub Secrets `CATMOA_GOOGLE_CLIENT_ID`, `CATMOA_GOOGLE_CLIENT_SECRET` → 빌드 시 `src/_secrets.py` 생성 (git 제외). 로컬은 동명 환경변수
- 상세 요구사항·결정 기록은 `docs/PRD.md`
- 테스트: `pytest` (pytest.ini에 pythonpath=. 설정됨)

## 컨텍스트 앵커
- intent: v0.1 기반 마일스톤 진행 중 (#1~#3 완료)
- changes_made: 골격·문서(#1), config.py(#2), llm/ 3종 어댑터 + 팩토리(#3, Ollama 실검증 완료)
- decisions: PRD §5 ADR 참조. Ollama는 `think:false` 필수(thinking 모델이 content를 비움). Claude 기본 모델 `claude-opus-5`. 공급자 생성자는 `client`/`transport` 주입 가능(테스트용)
- next_steps: #4 PDF 파서 → #5 HWPX → #6 HWP → #7 추출 스키마/프롬프트
