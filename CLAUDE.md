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
- intent: v0.1~v0.4 완료(#1~#19), v1.0 배포 진행 (#20·#21 완료, #22 README/릴리스 남음)
- changes_made: sources/coolm(리더+가짜 udb)·coolm_watcher, build.py·catmoa.spec·tools/make_icon.py·.github/workflows/build.yml. GitHub Pages 소개 페이지 docs/index.html (main /docs 소스, https://progh2.github.io/catmoa/ — 릴리스 API로 다운로드 링크 자동 갱신). 테스트 93개. 로컬 macOS arm64 빌드·실행 확인. CI workflow_dispatch 트리거함
- decisions: 워커/워처는 cat 위젯을 parent로 (종료 시 QObject 소유권 경고 방지). 쿨메신저 쪽지의 기준일은 ReceiveDate. macOS 앱은 LSUIElement(Dock 숨김). 산출물명 catmoa-{macos-arm64|windows-x86_64|linux-x86_64}. **Google 실제 로그인/등록 미검증** — .env 필요
- next_steps: CI 3-OS 빌드 결과 확인 → README 마무리 후 v1.0.0 태그 → Google 실검증(사용자 .env) → 검증 후 필요 시 fix
