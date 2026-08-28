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
- intent: v1.0.0 태그 push → Release 빌드 확인 → #22 종료
- changes_made: 전 마일스톤 구현(#1~#21). GitHub Pages docs/index.html (https://progh2.github.io/catmoa/). CI 3-OS 빌드 성공(workflow_dispatch). **Google 실검증 완료**(로그인·목록·이벤트/태스크 생성·삭제·앱 경로 E2E, 계정 ham@e-mirim.hs.kr). 테스트 93개
- decisions: 워커/워처는 cat 위젯을 parent로. 쿨메신저 기준일은 ReceiveDate. macOS 앱 LSUIElement. 산출물명 catmoa-{macos-arm64|windows-x86_64|linux-x86_64}. OAuth 동의 화면은 **프로덕션 게시**(테스트 모드는 refresh 토큰 7일 만료). oauthlib success_message는 text/plain → HTML 금지. 테스트는 `_load_dotenv`를 monkeypatch해 개발자 .env 격리. Linux offscreen segfault → tests/conftest.py 세션 정리 픽스처
- next_steps: Release v1.0.0 산출물 확인 → #22 close → 실사용 피드백(Windows 쿨메신저 실DB, 스캔 PDF 비전, Wayland) 반영
