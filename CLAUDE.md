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
- intent: v0.1~v0.3 완료(#1~#16) → v0.4 쿨메신저 연동
- changes_made: gsync/(auth·calendar·tasks·registrar), sources/inbox, AppController에 등록/인박스 연결. 테스트 87개. **Google 실제 로그인/등록은 아직 미검증** (.env에 클라이언트 ID 필요)
- decisions: google-auth 2.57은 expiry 없는 토큰을 즉시 만료 취급(테스트 가짜 토큰에 expiry 필요). 태스크 알람 = 마감일 09:00 30분 이벤트 "⏰ 제목". 인박스 항목 기준일은 태스크 updated 날짜. 등록/인박스 조회는 settings_dialog._Task(QThread)로 백그라운드
- next_steps: #17 coolm 리더 → #18 폴링 워처 → #19 설정 탭 연결 → v1.0 배포(#20~#22). 사용자가 .env 넣으면 Google 실검증
