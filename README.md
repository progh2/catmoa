# catmoa 🐱 — 교사를 위한 일정 수집 고양이

학교 곳곳에 흩어진 일정 정보(한글 문서, PDF, 쿨메신저 쪽지, 스크린샷, 복사한 텍스트)를
**고양이에게 던져주면** AI가 일정을 뽑아내고, 확인 한 번으로 **Google 캘린더 / Google Tasks**에 넣어주는
데스크톱 프로그램입니다. macOS · Windows · Linux를 모두 지원합니다.

> 교사 해커톤 프로젝트. 사용자 개입을 최소화하는 것이 목표입니다.

🏠 **소개·다운로드 페이지**: https://progh2.github.io/catmoa/

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
| LLM 선택 | Claude / ChatGPT(OpenAI) / Gemini(Google) / Solar(Upstage) / 로컬 Ollama 중 선택, 사용 가능한 모델 목록 조회, 연결 테스트. Solar는 이미지를 Upstage 문서 인식(OCR)으로 읽음 |
| 알람 | 등록 시 알람 여부 선택, 기본 "N분 전"은 설정에서 변경 |
| 자동 업데이트 | 시작 시 새 릴리스를 확인해 고양이 옆에 ⬆ 표시 → 클릭 또는 설정 → 업데이트 탭에서 **업데이트 설치** (내려받기 → 앱 종료 → 교체 → 재실행) |

## 지원 환경

- macOS (Apple Silicon / Intel), Windows 10+, Linux (X11/Wayland)
- 릴리스 페이지에서 OS별 실행 파일을 내려받으면 Python 설치 없이 바로 실행됩니다.
- LLM은 인터넷(Claude/OpenAI) 또는 로컬 Ollama 중 선택. 개인정보가 걱정되면 Ollama를 권장합니다.

## 설치

### 실행 파일 (권장)
[Releases](https://github.com/progh2/catmoa/releases)에서 OS에 맞는 파일을 내려받습니다. Python 설치가 필요 없습니다.

| OS | 파일 | 실행 |
|---|---|---|
| macOS (Apple Silicon) | `catmoa-macos-arm64.zip` | 압축 해제 → `catmoa.app`을 응용 프로그램 폴더로. 처음 실행 시 "악성 코드가 없음을 확인할 수 없음" 경고가 뜨면 아래 [macOS 첫 실행](#macos-첫-실행) 참고 |
| Windows 10/11 | `catmoa-windows-x86_64.zip` | 압축 해제 → `catmoa\catmoa.exe`. SmartScreen 경고가 뜨면 **추가 정보 → 실행** |
| Linux (x86_64) | `catmoa-linux-x86_64.tar.gz` | 압축 해제 → `./catmoa/catmoa`. X11 권장 (Wayland는 항상-위 창이 제한될 수 있음) |

#### macOS 첫 실행
서명·공증이 되지 않은 앱이라 macOS가 한 번 막습니다 (macOS 15 Sequoia부터는 "우클릭 → 열기"도 통하지 않습니다). 둘 중 하나로 한 번만 허용하면 됩니다.

- **시스템 설정으로 허용**: 앱을 실행해 경고가 뜨면 **완료** → **시스템 설정 → 개인정보 보호 및 보안** → 아래쪽 `"catmoa"이(가) 차단되었습니다` 옆 **그래도 열기** → 비밀번호/Touch ID
- **터미널로 격리 속성 제거**: `xattr -cr /Applications/catmoa.app` (zip 압축 해제 시 붙는 `com.apple.quarantine` 속성을 지웁니다)

앱은 Dock/작업표시줄에 나타나지 않고 고양이만 화면에 떠 있습니다. 종료는 고양이 **우클릭 → 종료**.

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
- 테스트: `pytest` (GUI 테스트는 `QT_QPA_PLATFORM=offscreen`)
- 로컬 빌드: `pip install pyinstaller && python build.py` → `dist/`
- 릴리스: `git tag v1.0.0 && git push --tags` → GitHub Actions가 macOS/Windows/Linux를 빌드해 Release에 첨부
- Google OAuth 클라이언트 (필수, 1회):
  1. [Google Cloud Console](https://console.cloud.google.com/) → 프로젝트 생성 → **API 및 서비스**에서 *Google Calendar API*, *Google Tasks API* 사용 설정
  2. OAuth 동의 화면 구성 (테스트 사용자에 사용할 계정 추가) → 사용자 인증 정보 → **OAuth 클라이언트 ID → 데스크톱 앱**
  3. 발급된 ID/보안 비밀을 저장소 **Settings → Secrets and variables → Actions → Repository secrets**에 등록:
     `CATMOA_GOOGLE_CLIENT_ID`, `CATMOA_GOOGLE_CLIENT_SECRET`
  4. 로컬 개발 시에는 프로젝트 루트에 `.env` 파일 (git 제외):
     ```
     CATMOA_GOOGLE_CLIENT_ID=xxxx.apps.googleusercontent.com
     CATMOA_GOOGLE_CLIENT_SECRET=GOCSPX-xxxx
     ```
  > 데스크톱 앱 클라이언트의 보안 비밀은 Google 정책상 비밀로 취급되지 않으므로 배포 바이너리에 포함해도 됩니다. 앱 검증 전에는 동의 화면의 **테스트 사용자**로 등록된 계정만 로그인할 수 있습니다.

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
