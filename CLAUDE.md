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
- intent: v1.3.0 — 쿨메신저 연결 테스트/지금 확인 버튼(#28). 사용자가 Windows(Parallels)에서 실제 쿨메신저로 테스트 중
- (이전) v1.2.0 릴리스 완료 (#25 위젯 크기 고정, #26 📅+✅ 동시 등록, #27 사용자 분류 규칙·태스크 카테고리)
- v1.2 메모: Decision.targets 집합(review_dialog), Registrar 조합 처리, ScheduleSettings.kind_rules/category_rules, ScheduleItem.category, PipelineWorker(options_factory), AppController.tasklists 캐시. 테스트 119개. 로컬 build.py 실행 시 src/_secrets.py 가 생겨 테스트가 실제 ID를 읽음 → 테스트에서 sys.modules["src._secrets"]=None 격리
- (이전) v1.1.0 릴리스 완료 (Gemini/Upstage 공급자 #23, 자동 업데이트 #24)
- changes_made: llm/gemini.py·upstage.py, updater.py(릴리스 확인·다운로드·교체 스크립트), 설정 '업데이트' 탭, 고양이 ⬆ 배지, CI 태그-버전 가드. 테스트 108개. **업데이트 E2E 검증**: 1.0.0 frozen 앱 → v1.1.0 릴리스로 자기 교체·재실행 성공(macOS). Google 실검증 완료(v1.0.0 때)
- decisions: 릴리스 시 `src/__init__.__version__` 을 먼저 올리고 같은 값으로 태그(v{ver}) — CI가 불일치면 실패. 업데이트는 frozen 에서만 설치(소스 실행은 git pull 안내). macOS 교체는 ditto 해제 + sh 스크립트(kill -0 대기 → mv → xattr -cr → open). Upstage 는 이미지를 Document Parse OCR 텍스트로 대체. httpx 모듈 함수는 transport 인자 불가 → Client 사용. Gemini/Upstage 실키 검증은 사용자가 직접(tools/check_llm.py)
- next_steps: Windows/Linux 에서 업데이트 교체 스크립트 실사용 검증(스크립트는 생성만 테스트됨) → 실사용 피드백 반영
