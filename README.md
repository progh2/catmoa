# catmoa 🐱 — 교사를 위한 일정 수집 고양이

학교 곳곳에 흩어진 일정 정보(한글 문서, PDF, 쿨메신저 쪽지, 스크린샷, 복사한 텍스트)를
**고양이에게 던져주면** AI가 일정을 뽑아내고, 확인 한 번으로 **Google 캘린더 / Google Tasks**에 넣어주는
데스크톱 프로그램입니다. macOS · Windows · Linux를 모두 지원합니다.

> 교사 해커톤 프로젝트. 사용자 개입을 최소화하는 것이 목표입니다.

## 한눈에 보는 흐름

```
  입력 (아무거나 던지기)                 처리                          출력
 ───────────────────────────    ─────────────────────────    ──────────────────────
  📄 .hwp / .hwpx / .pdf 드롭  ─┐
  🖼  스크린샷 붙여넣기 (호버+⌘V) ─┤   통합 큐 ──▶ 문서 파싱 ──▶ LLM 일정 추출
  📝 텍스트 붙여넣기            ─┼──▶  (순차 처리)   (텍스트/이미지)  (Claude·GPT·Ollama)
  💬 쿨메신저 새 쪽지 (30초 폴링) ─┤                                     │
  📥 Google Tasks 인박스 가져오기 ─┘                                     ▼
                                                     ┌─────────────────────────────┐
        (=^･ω･^=)  ◀── 표정으로 상태 표시 ───        │ 검토 창: 일정 목록          │
        고양이 위젯      idle / 먹는 중 / 완료 / 오류  │  ☑ 항목별 캘린더 ⇄ 태스크   │
                                                     │  ☑ 알람 on/off, N분 전       │
                                                     │  [모두 캘린더] [모두 태스크]  │
                                                     └──────────────┬──────────────┘
                                                                    ▼
                                                      📅 Google Calendar  /  ✅ Google Tasks
```

## 주요 기능

| 기능 | 설명 |
|---|---|
| 고양이 플로팅 위젯 | 항상 위에 떠 있는 작은 텍스트 고양이. 상황에 따라 표정이 바뀜 (처리 중이면 🍙 먹는 중) |
| 파일 드롭 | `.hwp`, `.hwpx`, `.pdf`(스캔본 포함), 이미지 파일 |
| 붙여넣기 | 고양이 위에 마우스를 올린 채 `Ctrl+V`/`⌘V` — 클립보드의 스크린샷·텍스트·파일 |
| 통합 큐 | 연달아 여러 개를 넣어도 차례대로 처리 |
| 일정 검토 | 추출된 일정을 목록으로 보여주고 항목별로 **캘린더/태스크 전환**, 알람 설정, 내용 편집 |
| Google 로그인 | JSON 파일 없이 브라우저 로그인만으로 연결 (토큰은 OS 키체인에 저장) |
| Google Tasks 인박스 | 휴대폰 등에서 대충 적어둔 "인박스" 목록의 항목을 불러와 분석·정리 (목록명 변경 가능) |
| 쿨메신저 연동 (선택) | 새로 받은 쪽지를 기본 30초 간격으로 확인해 자동 분석. 사용 여부·간격 설정 가능 (Windows) |
| LLM 선택 | Claude / ChatGPT(OpenAI) / 로컬 Ollama 중 선택, 사용 가능한 모델 목록 조회, 연결 테스트 |
| 알람 | 등록 시 알람 여부 선택, 기본 "N분 전"은 설정에서 변경 |

## 지원 환경

- macOS (Apple Silicon / Intel), Windows 10+, Linux (X11/Wayland)
- 릴리스 페이지에서 OS별 실행 파일을 내려받으면 Python 설치 없이 바로 실행됩니다.
- LLM은 인터넷(Claude/OpenAI) 또는 로컬 Ollama 중 선택. 개인정보가 걱정되면 Ollama를 권장합니다.

## 설치

### 실행 파일 (권장)
[Releases](https://github.com/progh2/catmoa/releases)에서 OS에 맞는 파일을 내려받습니다.

- macOS: `catmoa-macos.zip` → 압축 해제 → 처음 실행 시 우클릭 → 열기 (Gatekeeper)
- Windows: `catmoa-windows.zip` → 압축 해제 → `catmoa.exe` (SmartScreen 경고 시 "추가 정보 → 실행")
- Linux: `catmoa-linux.tar.gz` → 압축 해제 → `./catmoa`

### 소스에서 실행 (개발)
```bash
git clone https://github.com/progh2/catmoa.git
cd catmoa
./run.sh          # macOS / Linux
run.cmd           # Windows
```
Python 3.11 이상이 필요합니다. 가상환경 생성과 의존성 설치는 스크립트가 처리합니다.

## 첫 설정 (약 1분)

1. 고양이를 우클릭 → **설정**
2. **LLM** 탭: 공급자 선택 → API 키 입력(또는 Ollama 주소) → **모델 목록 불러오기** → 모델 선택 → **연결 테스트**
3. **Google** 탭: **로그인** → 브라우저에서 계정 선택 → 완료
4. (선택) **일반** 탭: 기본 대상(캘린더/태스크), 기본 알람 시간, 인박스 목록명
5. (선택, Windows) **쿨메신저** 탭: 사용 켜기, 확인 간격(초)

## 사용법

- 파일을 고양이 위로 끌어다 놓거나, 스크린샷을 찍은 뒤 고양이 위에 마우스를 올리고 붙여넣기
- 고양이가 🍙 먹는 동안 기다리면 검토 창이 뜸
- 항목별로 캘린더/태스크를 고르고 알람을 정한 뒤 **등록**
- 우클릭 메뉴 → **인박스 가져오기** 로 Google Tasks 임시 항목 정리

## 개인정보 안내

- 입력한 문서·이미지·쪽지 내용은 **선택한 LLM 공급자**로 전송됩니다. 외부 전송이 걱정되면 로컬 Ollama를 선택하세요.
- 쿨메신저 DB는 **읽기 전용 복사본**으로만 접근하며 원본을 수정하지 않습니다.
- Google 토큰은 OS 키체인(macOS Keychain / Windows Credential Manager / Linux Secret Service)에 저장됩니다.
- 이 프로그램은 별도 서버를 운영하지 않습니다. 데이터는 사용자 PC ↔ LLM ↔ Google 사이에서만 오갑니다.

## 개발

- 계획·아키텍처: [docs/PRD.md](docs/PRD.md)
- 진행 상황: [Milestones](https://github.com/progh2/catmoa/milestones) · [Issues](https://github.com/progh2/catmoa/issues)
- 테스트: `pytest`
- 빌드 비밀값 (GitHub Secrets): `CATMOA_GOOGLE_CLIENT_ID`, `CATMOA_GOOGLE_CLIENT_SECRET`
  — Google Cloud Console에서 **데스크톱 앱** 유형 OAuth 클라이언트를 만들어 등록. 로컬 개발 시에는 같은 이름의 환경변수로 대체 가능.

### 폴더 구조
```
catmoa/
├── main.py              # 진입점
├── run.sh / run.cmd     # 개발 실행 스크립트
├── src/
│   ├── config.py        # 설정 저장/복원
│   ├── llm/             # Claude / OpenAI / Ollama 어댑터
│   ├── parsers/         # PDF / HWPX / HWP 텍스트 추출
│   ├── extract/         # 일정 추출 스키마·프롬프트
│   ├── pipeline/        # 통합 처리 큐
│   ├── gsync/           # Google OAuth / Calendar / Tasks
│   ├── sources/         # 쿨메신저 udb, Tasks 인박스
│   └── ui/              # 고양이 위젯, 검토/설정 다이얼로그
├── tests/
└── docs/PRD.md
```

## 감사

- 쿨메신저 `.udb` 읽기 방식은 [dacisosl/coolm-helper](https://github.com/dacisosl/coolm-helper) (MIT)를 참고했습니다.

## 라이선스

MIT
