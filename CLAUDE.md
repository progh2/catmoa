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
- intent: v0.1·v0.2 완료(#1~#12) → v0.3 Google 연동 시작
- changes_made: config, llm/, parsers/, extract/, pipeline/(items·worker), ui/(cat_widget·review_dialog·settings_dialog·main_window AppController). 오프스크린 테스트 69개 + Ollama 실검증(E2E: 텍스트→큐→추출→검토창)
- decisions: PRD §5 ADR 참조. Ollama `think:false` 필수. ReviewDialog는 item.kind(event/task)→target(calendar/task) 매핑 주의. SettingsDialog는 GoogleAuthLike 프로토콜만 의존(v0.3에서 gsync.auth 주입). 결과 다이얼로그는 deque로 순차 표시. 로컬 Google 테스트는 `.env`(gitignore)에 CATMOA_GOOGLE_CLIENT_ID/SECRET
- next_steps: #13 OAuth(gsync/auth.py) → #14 Calendar → #15 Tasks → #16 인박스 → Registrar를 AppController.registrar에 연결
