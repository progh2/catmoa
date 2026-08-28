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
- intent: v1.4.9 — 고양이 크기 배율(#45: config.ui.cat_scale 0.5~3.0, cat_faces.load_cat_images(scale), CatWidget.set_scale/_lock_size, HairpinBadge.set_scale, 설정 일반 탭 QSlider). 랜딩 '놀아줘요' 카드(#44), README 아이콘(#43). v1.4.8 릴리스 완료
- (이전) v1.4.8 — 캘린더 설명·태스크 메모 하단에 원문(ScheduleItem.source_text, 설정 source_text_chars 기본 1500, 0=끔) (#42). v1.4.7: 설정 '교사' 탭(#41): TeacherSettings(출근/퇴근, 학교급 40/45/50, 교시 7개, 점심, autofill/describe) → 프롬프트 '시간표 참고' + 규칙 16. Ollama 실검증 4/4. v1.4.6 릴리스 완료(4방향 호버, 파비콘)
- (이전) v1.4.6 — 4방향 호버 시선(hover_tl/tr/bl/br, 사용자 이미지 4장 → cat-src, prepare_cat OPTIONAL 매핑), 파비콘(favicon.ico/apple-touch-icon, ?v=3), 랜딩 시선 추적. **규칙: 사용자 요청은 먼저 이슈 등록 후 커밋에 closes #N** (#33~#40 소급 등록, 마일스톤 v1.5 표정·편의)
- (이전) v1.4.5 — Windows 업데이트 "Security validation failure" 원인: 얼린 앱이 띄운 cmd 가 _PYI_*/_MEIPASS2 환경변수를 새 exe 에 상속 → updater.clean_env() 로 제거. 요청 표현 있으면 날짜 없어도 task(재요청 안전장치). 자동 실행(src/autostart.py: LaunchAgent/레지스트리 Run/.desktop). 업데이트 배지 = HairpinBadge(회전 빨간 핀, 이미지 모드는 오른쪽 귀 옆). README 현행화. ≤1.4.4 Windows 는 env 버그로 자동 업데이트 실패 → v1.4.5 수동 설치 1회
- (이전) v1.4.4 릴리스(쿨메신저 Windows 전용 잠금, 카드형 중복 창). v1.4.3 릴리스. v1.4.3: 쿨메신저 '지금 확인' 실패 사유 토스트, Memo 폴더 자동 탐지 후보 확장(APPDATA/PROGRAMDATA/계정별 하위). 다음 태그 v1.4.4 에 macOS 잠금 포함
- (이전) v1.4.2 — classifi_harness 반영(#32): 쿨메신저 '님이 보낸글 >>' 구분자, 역할(persona) 기반 scope 판정(irrelevant→항목 비움+토스트), 날짜 없는 task(undated, 태스크 due 생략), 행동형 제목 규칙. 토스트 알림(ui/toast.py: 컨테이너+windowOpacity — 최상위 QLabel+GraphicsEffect는 배경 안 그려짐). 업데이트 확인 403(API 한도) → github.com 리다이렉트 폴백. 앱 아이콘·랜딩을 새 고양이 이미지로. Edge SmartScreen 안내
- (이전) v1.4.1 — 등록 전 중복 검사(#31: gsync/dedupe.py + ui/dedupe_dialog.py, Decision.dedupe[target]=(action, existing, tasklist_id), Registrar skip/update/create) + 검토창 항목 체크박스 제거(📅/✅ 둘 다 끄면 제외). 테스트 152개
- (이전) v1.4.0 — 이미지 고양이 적용(사용자 원본 11장 → tools/prepare_cat.py 로 assets/cat/ 18파일 320px 생성, 원본은 assets/cat-src/ git 제외). 새 상태: searching(쿨메신저 폴링, 서류 찾는 고양이) / bored(5분 유휴) / empty(일정 없음) / annoyed(미지원 입력); sleeping 은 30분. 쿨메신저 인용 대화 분리(#30) + 달력 힌트 + 지난 항목 제외. 이미지 모드 QSS 는 상태 규칙 뒤에 둬야 투명 유지
- (이전) v1.3.3 — 사용자 Windows 는 **ARM64(Parallels)**: 업데이터가 arm64 산출물만 찾아 실패 → updater.asset_candidates() 로 x86_64 exe 폴백(x64 에뮬레이션). CI 는 x86_64 만 빌드. ≤1.3.2 Windows 클라이언트는 수동 설치 1회 필요
- (이전) v1.3.2 — 호버 시 위젯 크기 변동 수정(배지/⚙ 줄 자리 유지 + QFont 직접 지정으로 측정, 창 188×65 고정). v1.3.1 릴리스 성공(dmg/exe/tar.gz). Windows 1.3.1→1.3.2 자동 업데이트 실검증 대기
- (이전) v1.3.1 태그 발행 — 배포 형식 변경(Windows 단일 exe + macOS dmg) + **Windows 업데이트 스크립트 수정**: DETACHED_PROCESS 가 자식 콘솔 명령마다 검은 창("find 1234")을 띄웠고 `timeout` 이 stdin 없이 실패 → CREATE_NO_WINDOW + ping 대기 + taskkill/이동 재시도, AppController.quit 은 스레드 정리 후 3초 os._exit 폴백. ≤1.3.0 Windows 사용자는 스크립트 버그로 자동 업데이트 불가 → exe 수동 설치 1회 필요
- v1.3.1 메모: catmoa.spec win32 분기 onefile, build.py make_dmg(hdiutil, Applications 심링크), updater.asset_name_for_platform → dmg/exe/tar.gz, install_root Windows=exe 파일, extract .exe=그대로/.dmg=hdiutil attach→ditto, swap 스크립트 단일 파일 분기. Windows onefile 빌드·교체는 CI/실기기 미검증. ≤1.3.0 클라이언트는 zip 자산이 없어 릴리스 페이지 안내로 폴백(PRD D14). 테스트 125개
- (이전) v1.3.0 — 쿨메신저 연결 테스트/지금 확인 버튼(#28). 사용자가 Windows(Parallels)에서 실제 쿨메신저로 테스트 중
- (이전) v1.2.0 릴리스 완료 (#25 위젯 크기 고정, #26 📅+✅ 동시 등록, #27 사용자 분류 규칙·태스크 카테고리)
- v1.2 메모: Decision.targets 집합(review_dialog), Registrar 조합 처리, ScheduleSettings.kind_rules/category_rules, ScheduleItem.category, PipelineWorker(options_factory), AppController.tasklists 캐시. 테스트 119개. 로컬 build.py 실행 시 src/_secrets.py 가 생겨 테스트가 실제 ID를 읽음 → 테스트에서 sys.modules["src._secrets"]=None 격리
- (이전) v1.1.0 릴리스 완료 (Gemini/Upstage 공급자 #23, 자동 업데이트 #24)
- changes_made: llm/gemini.py·upstage.py, updater.py(릴리스 확인·다운로드·교체 스크립트), 설정 '업데이트' 탭, 고양이 ⬆ 배지, CI 태그-버전 가드. 테스트 108개. **업데이트 E2E 검증**: 1.0.0 frozen 앱 → v1.1.0 릴리스로 자기 교체·재실행 성공(macOS). Google 실검증 완료(v1.0.0 때)
- decisions: 릴리스 시 `src/__init__.__version__` 을 먼저 올리고 같은 값으로 태그(v{ver}) — CI가 불일치면 실패. 업데이트는 frozen 에서만 설치(소스 실행은 git pull 안내). macOS 교체는 ditto 해제 + sh 스크립트(kill -0 대기 → mv → xattr -cr → open). Upstage 는 이미지를 Document Parse OCR 텍스트로 대체. httpx 모듈 함수는 transport 인자 불가 → Client 사용. Gemini/Upstage 실키 검증은 사용자가 직접(tools/check_llm.py)
- next_steps: v1.3.1 태그 → CI 3-OS 빌드 성공 확인(특히 Windows onefile) → 랜딩에서 exe/dmg 직다운로드 확인 → Windows 에서 exe 자기 교체 업데이트 실검증 → Linux 교체 스크립트 실검증
