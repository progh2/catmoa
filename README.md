<p align="center"><img src="assets/icon.png" width="160" alt="catmoa 아이콘"></p>

<h1 align="center">catmoa — 교사를 위한 일정 수집 고양이</h1>

<p align="center">
학교 곳곳에 흩어진 일정·할 일(한글 문서, PDF, 쿨메신저 쪽지, 스크린샷, 복사한 텍스트, 휴대폰 메모)을<br>
<b>고양이에게 던져주면</b> AI가 뽑아내고, 확인 한 번으로 <b>Google 캘린더 / Google Tasks</b>에 넣어주는 데스크톱 프로그램입니다.<br>
macOS · Windows · Linux
</p>

<p align="center">🏠 <b>소개·다운로드 페이지</b>: <a href="https://progh2.github.io/catmoa/">progh2.github.io/catmoa</a> · <a href="https://github.com/progh2/catmoa/releases/latest">최신 릴리스</a></p>

> 교사 해커톤 프로젝트. 목표는 "사용자 개입 최소화"입니다.

<p align="center"><img src="assets/cat/idle_1.png" width="88" alt="대기"> <img src="assets/cat/hover_tr.png" width="88" alt="마우스 쳐다봄"> <img src="assets/cat/searching.png" width="88" alt="서류 찾는 중"> <img src="assets/cat/eating_1.png" width="88" alt="분석 중"> <img src="assets/cat/happy.png" width="88" alt="완료"> <img src="assets/cat/bored.png" width="88" alt="심심"></p>

## 한눈에 보는 흐름

```
  입력 (아무거나 던지기)                  처리                                출력
 ────────────────────────────    ────────────────────────────────    ──────────────────────
  📄 .hwp / .hwpx / .pdf 드롭   ─┐
  🖼  스크린샷 붙여넣기 (호버+⌘V)  ─┤   통합 큐 ─▶ 문서 파싱 ─▶ LLM 추출        📅 Google Calendar
  📝 텍스트 붙여넣기             ─┼─▶ (순차)     (텍스트/이미지)  ├─ 일정(event)   ✅ Google Tasks
  💬 쿨메신저 새 쪽지 (30초 폴링) ─┤                              ├─ 할 일(task, 날짜 없어도)     ▲
  📥 Google Tasks 인박스        ─┘                              └─ 내 업무와 무관 → 알림만     │
                                                                          │                 │
        고양이 위젯 ◀── 표정으로 상태 표시 ──┐        검토 창 ◀───────────┘                 │
        (대기·서류 찾기·냠냠·완료·오류·심심)  │   항목별 📅/✅ 선택, 목록(카테고리), 알람, 편집    │
                                          │        │                                       │
                                          └──▶ 중복 검사 ─▶ 건너뛰기 / 기존 갱신 / 새로 등록 ──┘
```

## 주요 기능

| 기능 | 설명 |
|---|---|
| 고양이 플로팅 위젯 | 항상 위에 떠 있는 작은 고양이. 상태별 표정(대기·놀람·서류 찾기·냠냠·완료·일정 없음·오류·심심·잠). 새 버전이 있으면 머리핀 배지 |
| 입력 | `.hwp`, `.hwpx`, `.pdf`(스캔본은 이미지로), 이미지, 텍스트 파일 드롭 · 고양이 위에 마우스를 올린 채 `Ctrl+V`/`⌘V`(스크린샷·텍스트·파일) · 우클릭 메뉴 |
| 통합 큐 | 연달아 여러 개를 넣어도 차례대로 처리 |
| AI 추출 | 일정(event)과 할 일(task) 분리, 상대 날짜("다음 주 목요일") 해석, 표·주간계획서의 여러 항목 추출, **요청이 있으면 날짜가 없어도 할 일**로 추출, 행동 문장 제목 |
| 내 역할 기반 필터 | 설정에 역할(예: "2학년 3반 담임, 정보 교과")을 적으면 다른 학년·교과·부서만의 쪽지는 등록 제안 없이 알림만 |
| 검토 창 | 항목별 **📅 캘린더 / ✅ 태스크** 체크(둘 다 가능 — 캘린더엔 마감일, 태스크엔 할 일), 태스크 목록(카테고리) 선택, 알람, 날짜·시간·장소·제목 편집, 원본 보기 |
| 중복 검사 | 등록 전 기존 캘린더/태스크와 비교해 비슷한 항목이 있으면 **건너뛰기 / 기존 갱신 / 새로 등록** 선택 |
| 사용자 분류 규칙 | 캘린더/태스크 분류 규칙, 태스크 카테고리(Google Tasks 목록) 규칙을 자유 텍스트로 |
| Google 로그인 | JSON 파일 없이 브라우저 로그인만으로 연결 (토큰은 OS 키체인) |
| Google Tasks 인박스 | 휴대폰 등에서 대충 적어둔 "인박스" 목록 항목을 불러와 분석·정리 (목록명 변경 가능, 없으면 생성 제안) |
| 쿨메신저 연동 (Windows) | 새 쪽지를 기본 30초 간격으로 확인해 자동 분석 (기본 꺼짐). 답장에 쌓인 이전 대화는 분리해 최근 내용 우선. 연결 테스트 · 지금 확인 버튼 |
| LLM 선택 | Claude / ChatGPT(OpenAI) / Gemini(Google) / Solar(Upstage) / 로컬 Ollama — 모델 목록 조회, 연결 테스트. Solar는 이미지를 Upstage 문서 인식(OCR)으로 |
| 알람 | 항목별 알람 여부·N분 전. Google Tasks는 알림이 없어 태스크 알람은 캘린더 알림 이벤트로(옵션) |
| 트레이 아이콘 · 숨기기 | 항상 떠 있는 트레이 아이콘. 고양이 우클릭 → **숨기기**로 트레이에 넣고, 아이콘 클릭으로 복귀(숨김 중엔 잠자는 고양이 아이콘). macOS는 메뉴 막대가 가득 차면 노치 뒤로 밀려 안 보일 수 있음 |
| 고양이 크기 | 설정 → 일반 → 슬라이더 0.5×~3.0× (저장 즉시 반영) |
| 자동 실행 · 자동 업데이트 | 설정에서 OS 시작 시 자동 실행 · 새 릴리스 확인 → 배지 → 설정에서 설치(내려받기 → 교체 → 재실행) |

## 지원 환경

- macOS (Apple Silicon), Windows 10/11 (x64, ARM은 x64 에뮬레이션), Linux x86_64 (X11 권장)
- 릴리스에서 실행 파일을 내려받으면 Python 설치가 필요 없습니다.
- LLM은 클라우드(Claude/OpenAI/Gemini/Upstage) 또는 로컬 Ollama. 개인정보가 걱정되면 Ollama를 권장합니다.

## 설치

### 실행 파일 (권장)
[Releases](https://github.com/progh2/catmoa/releases)에서 OS에 맞는 파일을 내려받습니다.

| OS | 파일 | 실행 |
|---|---|---|
| macOS (Apple Silicon) | `catmoa-macos-arm64.dmg` | 더블클릭 → `catmoa.app`을 Applications로 드래그. 처음 실행 시 경고가 뜨면 아래 [macOS 첫 실행](#macos-첫-실행) |
| Windows 10/11 | `catmoa-windows-x86_64.exe` | 단일 실행 파일 — 원하는 폴더에 두고 더블클릭 (첫 화면까지 몇 초). ARM Windows도 같은 파일. 첫 실행 경고는 [Windows 첫 실행](#windows-첫-실행) |
| Linux (x86_64) | `catmoa-linux-x86_64.tar.gz` | 압축 해제 → `./catmoa/catmoa`. `libEGL.so.1` 등이 없다는 오류가 나면 [Linux 준비](#linux-준비) |

앱은 Dock/작업표시줄에 나타나지 않고 고양이만 떠 있습니다. 종료·설정은 고양이 **우클릭**.

#### macOS 첫 실행
서명·공증이 되지 않은 앱이라 macOS가 한 번 막습니다 (macOS 15부터는 "우클릭 → 열기"도 통하지 않습니다).
- **시스템 설정으로 허용**: 경고에서 **완료** → **시스템 설정 → 개인정보 보호 및 보안** → 아래쪽 `"catmoa"이(가) 차단되었습니다` 옆 **그래도 열기**
- **터미널**: `xattr -cr /Applications/catmoa.app`

#### Windows 첫 실행
코드 서명이 없어 SmartScreen이 한 번 막습니다.
- **Edge가 다운로드를 차단**: 다운로드 목록에서 파일 위 **…** → **유지** → "자세히 표시" → **그래도 유지**. 계속 막히면 Chrome/Firefox로 받으세요.
- **실행 시 "Windows의 PC 보호" 창**: **추가 정보** → **실행**.
- 학교 PC처럼 정책으로 막힌 경우: 관리자에게 예외 등록을 요청하거나 [소스에서 실행](#소스에서-실행-개발).

#### Linux 준비
```bash
sudo apt-get install -y libegl1 libgl1 libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-keysyms1 libxcb-shape0 libxcb-xinerama0 libdbus-1-3 libfontconfig1 libglib2.0-0
```
디스플레이(X11/Wayland)가 없는 서버·컨테이너에서는 실행되지 않습니다.

### 소스에서 실행 (개발)
```bash
git clone https://github.com/progh2/catmoa.git
cd catmoa
./run.sh          # macOS / Linux
run.cmd           # Windows
```
Python 3.11 이상. 가상환경 생성과 의존성 설치는 스크립트가 처리합니다.

## 첫 설정 (약 1분)

1. 고양이 우클릭 → **설정**
2. **LLM** 탭: 공급자 → API 키(또는 Ollama 주소) → **모델 목록 불러오기** → 모델 선택 → **연결 테스트**
3. **Google** 탭: **로그인** → 브라우저에서 계정 선택
4. **분류 규칙** 탭 (선택): 내 역할, 캘린더/태스크 분류 규칙, 태스크 카테고리 규칙 · **교사** 탭: 출근·퇴근, 학교급(수업 시간), 교시·점심 시각 → "3교시", "점심시간", "퇴근 전" 해석에 사용
5. **일반** 탭 (선택): 기본 대상(자동/캘린더/태스크/둘 다), 알람 기본값, 인박스 목록명, 자동 실행
6. **쿨메신저** 탭 (Windows, 선택): 사용 켜기, 간격, 이전 대화 참고 길이 → **연결 테스트**

## 사용법

- 파일을 고양이 위로 끌어다 놓거나, 스크린샷을 찍은 뒤 고양이 위에 마우스를 올리고 붙여넣기
- 고양이가 서류를 뒤지고 밥을 먹는 동안 기다리면 **검토 창**이 뜸 → 항목별 📅/✅ 선택 → **등록**
- 비슷한 항목이 이미 있으면 **중복 확인 창**에서 처리 방법 선택
- 일정이 없으면 고양이가 시무룩해지고 "붙여넣은 텍스트에 일정이 없네요" 안내가 잠깐 뜸
- 우클릭 메뉴: 붙여넣기 · Google Tasks 인박스 가져오기 · 쿨메신저 지금 확인(Windows) · 설정 · 종료

## 이미지 고양이

고양이 그림은 `assets/cat/`의 PNG입니다. 직접 그린 그림으로 바꾸려면 [assets/cat/README.md](assets/cat/README.md)의 규격대로 파일을 넣으세요 (설정 폴더 `cat/`에 넣으면 빌드 없이 바로 반영). 원본에서 배포용 파일을 만드는 스크립트는 `tools/prepare_cat.py`.

## 개인정보 안내

- 입력한 문서·이미지·쪽지 내용은 **선택한 LLM 공급자**로 전송됩니다. 외부 전송이 걱정되면 로컬 Ollama를 선택하세요.
- 쿨메신저 DB는 **읽기 전용 복사본**으로만 접근하며 원본을 수정하지 않습니다.
- Google 토큰과 API 키는 OS 키체인(macOS Keychain / Windows Credential Manager / Linux Secret Service)에 저장됩니다.
- 별도 서버 없음. 데이터는 사용자 PC ↔ LLM ↔ Google 사이에서만 오갑니다. 업데이트 확인만 GitHub에 요청합니다.

## 개발

- 계획·아키텍처·결정 기록: [docs/PRD.md](docs/PRD.md) · 진행: [Milestones](https://github.com/progh2/catmoa/milestones) · [Issues](https://github.com/progh2/catmoa/issues)
- 테스트: `pytest` (GUI 테스트는 offscreen)
- 로컬 빌드: `pip install pyinstaller && python build.py` → `dist/`
- 릴리스: `src/__init__.py`의 `__version__`을 올리고 같은 값으로 `git tag vX.Y.Z && git push origin vX.Y.Z` → GitHub Actions가 3-OS 빌드 후 Release 첨부 (버전 불일치면 실패). 실행 중인 앱들은 배지로 새 버전을 알게 됩니다.
- 실검증 스크립트: `tools/check_llm.py <provider>` (모델 목록·연결·텍스트·이미지 추출), `tools/check_google.py --login --write`
- Google OAuth 클라이언트 (필수, 1회):
  1. [Google Cloud Console](https://console.cloud.google.com/) → 프로젝트 → **API 및 서비스**에서 *Google Calendar API*, *Google Tasks API* 사용 설정
  2. OAuth 동의 화면 구성 → **앱 게시**(프로덕션; 테스트 모드는 토큰이 7일마다 만료) → 사용자 인증 정보 → **OAuth 클라이언트 ID → 데스크톱 앱**
  3. ID/보안 비밀을 저장소 **Settings → Secrets and variables → Actions → Repository secrets**에 등록: `CATMOA_GOOGLE_CLIENT_ID`, `CATMOA_GOOGLE_CLIENT_SECRET`
  4. 로컬 개발 시에는 프로젝트 루트에 `.env` (git 제외):
     ```
     CATMOA_GOOGLE_CLIENT_ID=xxxx.apps.googleusercontent.com
     CATMOA_GOOGLE_CLIENT_SECRET=GOCSPX-xxxx
     ```
  > 데스크톱 앱 클라이언트의 보안 비밀은 Google 정책상 비밀로 취급되지 않으므로 배포 바이너리에 포함해도 됩니다.
- 코드 서명(선택): Windows SmartScreen/Edge 차단을 없애려면 **Azure Trusted Signing**(월 약 $10) 또는 OV/EV 인증서로 exe 서명, macOS는 Apple Developer($99/년)로 서명·공증. 인증서가 준비되면 워크플로우에 서명 단계를 추가하면 됩니다.

### 폴더 구조
```
catmoa/
├── main.py                  # 진입점
├── build.py · catmoa.spec   # PyInstaller (Windows 단일 exe, macOS dmg, Linux tar.gz)
├── assets/cat/              # 고양이 표정 이미지 (배포용 320px)
├── src/
│   ├── config.py            # 설정 저장/복원 (platformdirs + keyring)
│   ├── updater.py           # 자동 업데이트 (GitHub Releases)
│   ├── autostart.py         # OS 시작 시 자동 실행
│   ├── llm/                 # Claude / OpenAI / Gemini / Upstage / Ollama 어댑터
│   ├── parsers/             # PDF / HWPX / HWP 텍스트 추출
│   ├── extract/             # 일정 추출 스키마·프롬프트·추출기
│   ├── pipeline/            # 통합 처리 큐
│   ├── gsync/               # Google OAuth / Calendar / Tasks / 등록 / 중복 검사
│   ├── sources/             # 쿨메신저 udb·워처, Tasks 인박스
│   └── ui/                  # 고양이 위젯, 검토·중복·설정 다이얼로그, 토스트
├── tests/
├── tools/                   # 아이콘·고양이 이미지 생성, 실검증 스크립트
└── docs/                    # PRD, GitHub Pages 소개 페이지
```

## 감사

- 쿨메신저 `.udb` 읽기 방식은 [dacisosl/coolm-helper](https://github.com/dacisosl/coolm-helper) (MIT)를 참고했습니다.

## 라이선스

MIT
