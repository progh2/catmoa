# catmoa PRD (Product Requirements Document)

버전 0.1 · 2026-08-28 · 교사 해커톤

## 1. 개요

### 문제
교사에게 오는 일정 정보는 형식이 제각각이다. 공문(hwp/hwpx/pdf), 쿨메신저 쪽지, 단체방 스크린샷,
휴대폰 메모에 급히 적은 할 일… 이것을 매번 읽고 손으로 캘린더에 옮기는 일은 귀찮고 자주 빠뜨린다.

### 해결
**"고양이한테 던지면 캘린더에 들어간다."**
어떤 형식이든 플로팅 고양이 위젯에 드롭/붙여넣기 하면 AI가 일정을 추출하고, 사용자는 목록을 훑어보고
캘린더/태스크 방향과 알람만 정해 등록한다. 쿨메신저와 Google Tasks 인박스는 자동으로 끌어온다.

### 목표 (측정 가능)
- 공문 1건 → 캘린더 등록까지 **클릭 3회 이내** (드롭 → 확인 → 등록)
- Google 연결에 **JSON 파일 다운로드 없음** — 브라우저 로그인만
- macOS / Windows / Linux **동일 기능**, 릴리스에서 실행 파일 다운로드
- 처리 중 **UI가 멈추지 않음**, 연속 입력은 순서대로 처리

### 비목표 (v1.0 범위 밖)
- 자체 캘린더 뷰 (Google 앱을 보면 됨)
- 일정 수정/삭제 동기화 (등록만 한다)
- 정규식 기반 오프라인 파싱 (LLM에 위임; Ollama가 오프라인 대안)
- 자동 업데이트

## 2. 사용자와 시나리오

**주 사용자:** 초·중·고 교사. 기술 배경 없음. 학교 PC는 대부분 Windows, 개인 노트북은 macOS도 많음.

| # | 시나리오 | 입력 | 기대 |
|---|---|---|---|
| S1 | 교육청 공문 hwp 수신 | 파일 드롭 | 연수 일정·제출 기한이 각각 추출, 연수=캘린더 / 제출=태스크 제안 |
| S2 | 학부모 단체방 스크린샷 | ⌘V 붙여넣기 | 이미지에서 상담 일정 추출 |
| S3 | 쿨메신저로 "내일 3시 회의" 쪽지 | 자동 폴링 | 30초 내 고양이가 반응, 검토 창 표시 (수신일 기준 "내일" 해석) |
| S4 | 출근길에 휴대폰 Tasks 인박스에 "금요일 가정통신문" 메모 | 인박스 가져오기 | 날짜가 붙은 태스크로 정리, 원본 완료 처리 |
| S5 | 복사한 메일 본문 | 텍스트 붙여넣기 | 여러 일정 동시 추출 |

## 3. 기능 요구사항

### FR-1 입력 소스
| 코드 | 요구사항 |
|---|---|
| FR-1.1 | `.hwpx` — zip 내 `Contents/section*.xml` 파싱, 문단·표 텍스트 추출 (stdlib) |
| FR-1.2 | `.hwp` (5.0) — OLE `BodyText/Section*` → zlib 해제 → `HWPTAG_PARA_TEXT` 파싱. 배포용/암호 문서는 오류 안내 |
| FR-1.3 | `.pdf` — 텍스트 레이어 추출(pdfplumber). 텍스트가 거의 없으면(스캔본) 페이지를 이미지로 렌더(pypdfium2)해 비전 LLM에 전달 |
| FR-1.4 | 이미지 파일 / 클립보드 이미지 — 비전 LLM에 직접 전달 |
| FR-1.5 | 텍스트 드롭 / 클립보드 텍스트 |
| FR-1.6 | 호버 붙여넣기 — 고양이 위에 마우스가 있을 때 `Ctrl+V`/`⌘V` 를 가로채 클립보드 내용 수신. 우클릭 메뉴 "붙여넣기"도 제공 |
| FR-1.7 | 쿨메신저 — `%LOCALAPPDATA%\CoolMessenger\Memo\*.udb` (SQLite WAL) 읽기 전용 폴링. 기본 30초, 설정 가능, 기본 **꺼짐** |
| FR-1.8 | Google Tasks 인박스 — 설정된 목록(기본 "인박스")의 미완료 태스크를 가져와 분석 |

### FR-2 처리
| 코드 | 요구사항 |
|---|---|
| FR-2.1 | 통합 큐 — 모든 입력은 `InputItem`으로 정규화되어 단일 큐에 들어가고 워커 스레드가 순차 처리 |
| FR-2.2 | LLM 추출 — 기준일(오늘 또는 메시지 수신일)을 프롬프트에 주입, 상대 날짜("내일", "다음 주 화") 해석 |
| FR-2.3 | 출력 스키마 — `ScheduleItem{title, start, end, all_day, kind(event/task), location, notes, alarm_minutes, confidence}` 리스트 |
| FR-2.4 | 응답 검증 — pydantic 검증, JSON 깨짐 시 1회 재요청, 그래도 실패면 오류 상태 |
| FR-2.5 | kind 제안 — "제출/마감/까지" 계열은 task, 시간이 있는 행사는 event로 LLM이 1차 제안, 사용자가 변경 |

### FR-3 검토 UI
| 코드 | 요구사항 |
|---|---|
| FR-3.1 | 추출 항목을 목록으로 표시. 항목별 체크박스, 제목·일시·장소 인라인 편집 |
| FR-3.2 | 항목별 **📅 캘린더 / ✅ 태스크 체크박스** (둘 다 가능). 둘 다면 캘린더엔 "(마감)" 일정, 태스크엔 할 일. 태스크 목록(카테고리) 콤보 |
| FR-3.3 | 일괄 버튼: 모두 📅 / 모두 ✅ / 모두 📅+✅ / 모두 선택 / 모두 해제 |
| FR-3.4 | 항목별 알람 on/off + 분 단위 (기본값은 설정에서) |
| FR-3.5 | 등록 후 결과 요약 (성공 n건 / 실패 사유) |
| FR-3.6 | 원본 미리보기 (추출 근거 텍스트/이미지 축소본) |
| FR-3.7 | 등록 전 **중복 검사**: 캘린더(항목 기간 ±1일 이벤트) / 태스크(대상 목록 미완료, 마감 ±3일)와 제목 유사도 ≥0.75 → 항목별 건너뛰기 / 기존 갱신(일시·메모 덮어쓰기, 제목 유지) / 새로 등록 선택 |
| FR-3.8 | 항목 선택 체크박스 없음 — 📅/✅ 둘 다 끄면 등록 안 함 (v1.4.1, 혼동 방지) |

### FR-4 Google 연동
| 코드 | 요구사항 |
|---|---|
| FR-4.1 | OAuth 2.0 loopback flow(`InstalledAppFlow`). 클라이언트 ID/Secret은 빌드 시 앱에 내장 → 사용자는 JSON 불필요 |
| FR-4.2 | refresh token은 keyring 저장, 재시작 시 자동 로그인. 로그아웃 시 삭제 |
| FR-4.3 | 스코프: `calendar.events`, `calendar.readonly`, `tasks` |
| FR-4.4 | Calendar: 캘린더 목록 조회·기본 캘린더 선택, 이벤트 생성(종일/시간), `reminders.overrides` popup |
| FR-4.5 | Tasks: 목록 조회·기본 목록 선택, 태스크 생성(`due`, `notes`) |
| FR-4.6 | Tasks 알람 — Tasks API는 알림을 지원하지 않으므로 알람 선택 시 **캘린더에 알림 이벤트를 함께 생성**하는 옵션 제공 |
| FR-4.7 | 인박스 가져오기 후 원본 태스크 완료 처리 (옵션, 기본 켜짐) |

### FR-5 LLM 설정
| 코드 | 요구사항 |
|---|---|
| FR-5.1 | 공급자: Claude(anthropic) / OpenAI / Gemini(REST) / Upstage Solar(OpenAI 호환) / Ollama |
| FR-5.2 | 모델 목록 조회 — Claude·OpenAI·Upstage `models.list`, Gemini `GET /v1beta/models`, Ollama `GET /api/tags` |
| FR-5.6 | Solar 채팅 모델은 이미지를 받지 않으므로 Upstage Document Parse(OCR)로 텍스트화 후 분석 |
| FR-5.7 | 사용자 분류 규칙(설정 → 분류 규칙): event/task 판단 규칙, 태스크 카테고리 규칙을 프롬프트에 주입. 카테고리 = Google Tasks 목록 이름, 응답 `category` → 검토창 목록 자동 선택 |
| FR-5.3 | 연결 테스트 — 짧은 프롬프트로 응답 확인, 결과·지연시간 표시 |
| FR-5.4 | API 키는 keyring 저장 |
| FR-5.5 | 비전 미지원 모델 선택 시 이미지 입력에 경고 |

### FR-6 고양이 위젯
| 코드 | 요구사항 |
|---|---|
| FR-6.1 | 프레임리스, 투명 배경, 항상 위, 드래그로 이동, 위치 저장/복원 |
| FR-6.2 | 텍스트 표정 상태머신: `idle` `hover` `thinking` `eating` `happy` `error` `sleeping` |
| FR-6.3 | 큐 대기 수를 툴팁/작은 배지로 표시 |
| FR-6.4 | 우클릭 메뉴: 붙여넣기, 인박스 가져오기, 설정, 종료 |
| FR-6.5 | ~~호버 시 ⚙ 아이콘~~ → 제거(v1.3.4, 사용자 요청). 설정은 우클릭 메뉴. 새 버전이 있을 때만 ⬆ 배지 표시 |

### FR-7 설정
| 코드 | 항목 | 기본값 |
|---|---|---|
| FR-7.1 | LLM 공급자 / 모델 / 키 / Ollama URL | Ollama, `http://localhost:11434` |
| FR-7.2 | 기본 대상 (캘린더/태스크/LLM 제안) | LLM 제안 |
| FR-7.3 | 기본 알람 켬 여부 / 분 전 | 켬 / 30분 |
| FR-7.4 | 태스크 알람 → 캘린더 알림 이벤트 생성 | 켬 |
| FR-7.5 | 기본 캘린더 / 기본 태스크 목록 / 인박스 목록명 | primary / 기본 목록 / "인박스" |
| FR-7.6 | 인박스 가져오기 후 원본 완료 처리 | 켬 |
| FR-7.7 | 쿨메신저 사용 여부 / 폴링 간격(초) / Memo 경로 | 꺼짐 / 30 / 자동 탐지 |
| FR-7.8 | 위젯 위치, 시작 시 자동 실행(후순위) | — |

### FR-8 배포
| 코드 | 요구사항 |
|---|---|
| FR-8.1 | PyInstaller 빌드 — macOS .app→dmg, Windows 단일 exe(onefile), Linux onedir→tar.gz. OS별 아이콘 |
| FR-8.2 | GitHub Actions 매트릭스 (macos-latest, ubuntu-latest, windows-latest), 태그 push 시 Release 생성 및 산출물 첨부 |
| FR-8.3 | Secrets `CATMOA_GOOGLE_CLIENT_ID`, `CATMOA_GOOGLE_CLIENT_SECRET` → 빌드 시 `src/_secrets.py` 생성 (git 제외) |

## 4. 아키텍처

```
┌──────────────────────────── UI (PySide6, 메인 스레드) ───────────────────────────┐
│  CatWidget ──(drop/paste)──▶ InputItem ──▶ PipelineWorker.enqueue()              │
│      ▲ 상태 시그널                              │                                 │
│  ReviewDialog ◀──(items_ready 시그널)───────────┘                                 │
│      │ 등록 요청                                                                  │
│      ▼                                                                            │
│  Registrar ──▶ gsync.calendar / gsync.tasks  (별도 스레드에서 API 호출)            │
│  SettingsDialog ──▶ config / llm.check / gsync.auth                              │
└──────────────────────────────────────────────────────────────────────────────────┘
           ▲                                   ▲
   sources.coolm (QTimer 폴링)        sources.inbox (수동 트리거)

┌────────────── PipelineWorker (QThread) ──────────────┐
│ queue.Queue ─▶ parsers.dispatch(item) ─▶ text/images │
│             ─▶ extract.Extractor(llm).run(...)       │
│             ─▶ emit items_ready(list[ScheduleItem])  │
└──────────────────────────────────────────────────────┘
```

### 모듈
| 모듈 | 책임 | 외부 의존 |
|---|---|---|
| `src/config.py` | 설정 dataclass, JSON 저장(platformdirs), 비밀은 keyring | platformdirs, keyring |
| `src/llm/` | `LLMProvider` 추상 (`list_models`, `check`, `complete_json`) + 3개 구현 | anthropic, openai, httpx |
| `src/parsers/` | `dispatch(path\|bytes) -> ParsedInput(text, images)` | pdfplumber, pypdfium2, olefile |
| `src/extract/` | 스키마, 프롬프트, 추출기 | pydantic |
| `src/pipeline/` | `InputItem`, `PipelineWorker` | PySide6 |
| `src/gsync/` | `auth`, `calendar`, `tasks` | google-auth(-oauthlib), google-api-python-client |
| `src/sources/` | `coolm`(udb 리더+워처), `inbox` | sqlite3 |
| `src/ui/` | `cat_widget`, `review_dialog`, `settings_dialog`, `styles` | PySide6 |

### 데이터 흐름의 핵심 객체
```python
class InputItem:            # 큐에 들어가는 단위
    kind: Literal["file", "text", "image", "coolm", "inbox_task"]
    payload: Path | str | bytes
    source_label: str        # UI 표시용 ("공문.hwp", "쿨메신저: 홍길동")
    reference_date: date     # 상대 날짜 기준일 (쪽지는 수신일)
    origin_ref: str | None   # inbox 태스크 id 등 후처리용

class ScheduleItem(BaseModel):   # LLM 출력 단위
    title: str
    start: datetime | date
    end: datetime | date | None
    all_day: bool
    kind: Literal["event", "task"]
    location: str | None
    notes: str | None
    alarm_minutes: int | None    # None = 알람 없음
    confidence: float
```

## 5. 핵심 결정 기록 (ADR 요약)

| # | 결정 | 대안 | 이유 |
|---|---|---|---|
| D1 | GUI = PySide6 | Electron, Tauri, Tk | 순수 Python 단일 스택, 3-OS, 드롭/클립보드/투명창 지원, LGPL |
| D2 | 파싱은 순수 Python wheel만 | poppler/LibreOffice 호출 | 3-OS PyInstaller 빌드 단순화, 사용자 설치 부담 0 |
| D3 | HWP는 직접 파서 | pyhwp | pyhwp의 Py3 지원 불안정. 텍스트만 필요하므로 PARA_TEXT 파싱으로 충분 |
| D4 | 일정 추출은 LLM 전담 | 정규식 파서 병행 | 형식 다양성(표, 이미지) 대응. 오프라인 요구는 Ollama로 충족 |
| D5 | OAuth 클라이언트 내장 | 사용자별 JSON | "JSON 없이 로그인" 요구. Google 정책상 데스크톱 앱 secret은 비밀 아님 |
| D6 | 토큰·API 키는 keyring | 평문 파일 | OS 표준 보안 저장소. keyring 실패 시 파일 폴백 + 경고 |
| D7 | Tasks 알람 = 캘린더 알림 이벤트 | 미지원 | Tasks API 알림 없음. 사용자 요구 충족을 위한 우회, 옵션으로 제공 |
| D8 | 쿨메신저 기본 꺼짐 | 기본 켜짐 | 쪽지 원문이 LLM으로 전송됨. 명시적 동의 후 켜기 |
| D9 | 쿨메신저 접근 = 복사본 읽기 전용 | 원본 직접 열기 | coolm-helper 검증 방식. 원본 무손상 보장 |
| D10 | 패키지명 `pipeline`, `gsync` | `queue`, `google` | stdlib·google 네임스페이스 충돌 회피 |
| D11 | Python 3.12 빌드 | 3.13 | 3-OS wheel 가용성이 가장 안정적 |
| D12 | 자동 업데이트 = GitHub Releases 조회 + 외부 교체 스크립트 | 인스톨러/서명 프레임워크 | 서버 없이 동작. 실행 중 바이너리는 자기 교체 불가 → 종료 대기 스크립트가 폴더 교체·재실행. frozen 에서만 설치 |
| D14 | 배포 형식: Windows 단일 exe + macOS dmg | onedir zip | 랜딩에서 클릭 즉시 실행 파일. exe 는 기동 시 임시 해제로 수 초 느리지만 교사 사용자에게 "압축 풀기" 단계 제거가 더 중요. .app 은 폴더라 dmg 컨테이너 필요. ≤1.3.0 클라이언트는 zip 자산을 못 찾아 릴리스 페이지 안내로 폴백 |
| D13 | Upstage 이미지 입력은 Document Parse OCR 경유 | 비전 미지원으로 이미지 거부 | Solar 채팅은 이미지 불가. 한국어 OCR 품질이 좋아 공문 스캔에 오히려 유리 |
| D14 | 📅+✅ 동시 등록 시 캘린더는 종일 "(마감)" 일정 + 알람 전날 17:00 | 09:00 타임 이벤트 | 마감은 종일 배너가 직관적. Google 종일 알림은 자정 기준이라 "N분 전"이 무의미 → 관례(전날 17:00) 고정. 시각이 있는 마감은 그 시각 + 사용자 N분 |
| D15 | 태스크 카테고리 = Google Tasks 목록 | 앱 자체 태그 | 휴대폰 Tasks 앱에서 그대로 보이고, 사용자가 이미 만든 목록을 활용. 위젯 크기는 표정 프레임 최대치로 고정 |

## 6. 개인정보

- 문서·이미지·쪽지 원문은 선택한 LLM으로 전송된다. 설정 화면과 쿨메신저 활성화 시 명시 안내.
- 로컬 처리를 원하면 Ollama 선택 (llava/qwen2.5-vl 등 비전 모델 권장).
- 쿨메신저 udb는 임시 폴더 복사 → `mode=ro` → 사용 후 삭제. 원본 파일 mtime 불변.
- Google에는 사용자가 검토 창에서 확인한 항목만 전송된다.
- 별도 서버 없음. 텔레메트리 없음.

## 7. 마일스톤

| 마일스톤 | 이슈 | 내용 |
|---|---|---|
| v0.1 기반 | #1–#7 | 골격, 설정, LLM 어댑터, 파서 3종, 추출 스키마 |
| v0.2 GUI | #8–#12 | 고양이 위젯, 입력 수신, 큐, 검토/설정 다이얼로그 |
| v0.3 Google | #13–#16 | OAuth, Calendar, Tasks, 인박스 |
| v0.4 쿨메신저 | #17–#19 | udb 리더, 폴링 워처, 설정 탭 |
| v1.0 배포 | #20–#22 | PyInstaller, Actions, README |

## 8. 열린 질문 / 리스크

| 항목 | 대응 |
|---|---|
| Google OAuth 앱 검증 — 미검증 앱은 테스트 사용자 100명 제한, "확인되지 않은 앱" 경고 | 해커톤 단계는 테스트 모드. 배포 확대 시 검증 신청 |
| macOS Gatekeeper / Windows SmartScreen 경고 | README 안내. 서명은 후순위 |
| 호버 중 Ctrl+V 가로채기 — 포커스 없는 창은 키 입력을 받지 못함 | 호버 진입 시 `activateWindow()` 로 포커스 획득, 이탈 시 이전 앱으로 복귀는 OS 제약 수용. 우클릭 "붙여넣기"를 항상 제공 |
| Wayland에서 항상-위/위치 지정 제한 | X11 우선, Wayland는 best effort |
| 쿨메신저 스키마 변경 | 시작 시 컬럼 검증, 실패 시 기능 비활성 + 안내 |
| HWP 표 안의 일정 | 셀 텍스트를 줄 단위로 나열해 LLM에 전달. 필요 시 마크다운 표로 재구성 |
