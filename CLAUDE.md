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
- intent: v0.1 기반 완료(#1~#7) → v0.2 GUI 시작
- changes_made: config.py, llm/(3종 어댑터), parsers/(pdf·hwpx·hwp, 실제 공문 검증), extract/(schema·prompts·extractor, Ollama gemma4 실검증)
- decisions: PRD §5 ADR 참조. Ollama `think:false` 필수. LLM에는 date/time 문자열 필드를 요구하고 schema.normalize()에서 datetime화. 실검증 결과 gemma4:latest는 정확, e2b는 월 추정 오류 → 프롬프트 규칙 11 추가. 샌드박스가 ~/Documents 접근 불가 → 샘플은 ~/Downloads 사용
- next_steps: #8 고양이 위젯 → #9 입력 수신 → #10 큐 → #11 검토 다이얼로그 → #12 설정 다이얼로그
