# 이미지 고양이

이 폴더에 PNG 를 넣으면 텍스트 고양이 대신 이미지로 표시됩니다 (빌드에 포함).
빌드 없이 바로 써보려면 설정 폴더의 `cat/` 에 넣으세요:
macOS `~/Library/Application Support/catmoa/cat/`, Windows `%APPDATA%\catmoa\cat\`, Linux `~/.config/catmoa/cat/`

| 파일 | 상태 |
|---|---|
| `idle.png` | 기본 (**필수** — 없는 상태는 이걸로 대체) |
| `hover.png` | 마우스 올림 |
| `drag.png` | 파일을 끌어와 놓기 직전 |
| `thinking.png` | 문서 읽는 중 |
| `eating.png` | AI 분석 중 |
| `happy.png` | 완료 |
| `error.png` | 오류 |
| `annoyed.png` | 지원하지 않는 입력을 받음 |
| `empty.png` | 일정을 찾지 못함 |
| `searching.png` | 쿨메신저 새 쪽지 확인 중 |
| `bored.png` | 5분 이상 입력 없음 |
| `sleeping.png` | 30분 이상 입력 없음 |

현재 파일은 `assets/cat-src/`(원본, git 제외)에서 `python tools/prepare_cat.py` 로 생성한 320px 이미지입니다.
원본을 바꾸면 그 스크립트를 다시 실행하세요 (매핑은 스크립트의 `MAPPING`).

- PNG, 배경 투명, **모든 파일 같은 캔버스 크기** (예: 256×256). 화면엔 절반 크기(레티나 2x)로 표시되고 폭 220px 를 넘지 않게 축소됩니다.
- 애니메이션: `eating_1.png`, `eating_2.png`… 처럼 번호를 붙이면 순환 재생 (상태별 재생 간격은 `src/ui/styles.py` 의 `FRAME_MS`).
- 큐 개수·⬆ 배지는 이미지 위쪽 줄에 그대로 표시됩니다.
