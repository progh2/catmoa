#!/usr/bin/env python3
"""태그 사이의 커밋으로 한국어 릴리스 노트를 만든다.

릴리스 페이지와 **앱 안의 업데이트 창**에 그대로 쓰인다. GitHub 의 자동 생성 노트는
PR 없이 main 에 직접 커밋하는 이 저장소에서는 "Full Changelog" 한 줄만 만들어 쓸모가 없다.

    python tools/release_notes.py                 # 최신 태그
    python tools/release_notes.py --tag v1.4.14   # 특정 태그
    python tools/release_notes.py --tag v1.4.14 --previous v1.4.12
"""
from __future__ import annotations

import argparse
import re
import subprocess

# 커밋 타입 → 사용자가 읽을 제목 (순서대로 표시)
SECTIONS = [
    ("feat", "✨ 새로워진 점"),
    ("fix", "🐛 고친 것"),
    ("perf", "⚡ 빨라진 것"),
    ("docs", "📝 문서"),
    ("refactor", "🧹 정리"),
    ("chore", "🔧 그 밖에"),
    ("test", "🔧 그 밖에"),
]
TYPE_TITLE = dict(SECTIONS)
ORDER = list(dict.fromkeys(t for _, t in SECTIONS))

DOWNLOAD = """
## 내려받기

| 내 컴퓨터 | 받을 파일 | 실행 |
|---|---|---|
| Windows 10/11 | `catmoa-windows-x86_64.exe` | 원하는 폴더에 두고 더블클릭 (ARM Windows도 같은 파일) |
| macOS (Apple Silicon) | `catmoa-macos-arm64.dmg` | 열어서 `catmoa.app` 을 응용 프로그램으로 끌어다 놓기 |
| Linux (x86_64) | `catmoa-linux-x86_64.tar.gz` | 압축을 풀고 `./catmoa/catmoa` |

이미 catmoa 를 쓰고 계시면 고양이 옆 ⬆ 배지나 **설정 → 업데이트** 에서 바로 올릴 수 있습니다.

처음 실행할 때 Windows SmartScreen 이나 macOS 보안 경고가 뜨면
[README 의 첫 실행 안내](https://github.com/progh2/catmoa#설치)를 봐 주세요 (코드 서명이 없어서 그렇습니다).
"""


def run(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout.strip()


def previous_tag(tag: str) -> str | None:
    tags = [t for t in run("tag", "--list", "v*", "--sort=-v:refname").splitlines() if t]
    if tag in tags:
        i = tags.index(tag)
        return tags[i + 1] if i + 1 < len(tags) else None
    return tags[0] if tags else None


def clean(subject: str) -> tuple[str, str]:
    """'feat: 설명 (closes #12, closes #13)' → ('feat', '설명 (#12, #13)')."""
    m = re.match(r"^(\w+)(?:\([^)]*\))?:\s*(.+)$", subject)
    kind, text = (m.group(1).lower(), m.group(2)) if m else ("chore", subject)
    issues = re.findall(r"#(\d+)", text)
    text = re.sub(r"\s*\((?:closes?|fixes?|resolves?)\s*#\d+(?:\s*,\s*(?:closes?|fixes?|resolves?)?\s*#\d+)*\)", "", text, flags=re.I)
    text = re.sub(r"\s*\(#\d+(?:\s*,\s*#\d+)*\)", "", text).strip(" ,·")
    text = re.sub(r",?\s*버전 \d+\.\d+\.\d+$", "", text).strip(" ,·")
    return kind, text + (f" (#{', #'.join(dict.fromkeys(issues))})" if issues else "")


def collect(tag: str, prev: str | None) -> dict[str, list[str]]:
    rng = f"{prev}..{tag}" if prev else tag
    out: dict[str, list[str]] = {}
    for line in run("log", "--no-merges", "--pretty=format:%s", rng).splitlines():
        if not line.strip():
            continue
        kind, text = clean(line)
        if not text or re.fullmatch(r"버전 \d+\.\d+\.\d+.*", text):
            continue
        title = TYPE_TITLE.get(kind, "🔧 그 밖에")
        if text not in out.setdefault(title, []):
            out[title].append(text)
    return out


def render(tag: str, prev: str | None, groups: dict[str, list[str]], repo: str) -> str:
    version = tag.lstrip("vV")
    parts = [f"# catmoa {version}", ""]
    if groups:
        for title in ORDER:
            items = groups.get(title)
            if items:
                parts.append(f"## {title}")
                parts += [f"- {it}" for it in items]
                parts.append("")
    else:
        parts += ["작은 수정만 있었습니다.", ""]
    parts.append(DOWNLOAD.strip())
    parts.append("")
    if prev:
        parts.append(f"**전체 변경 내역**: https://github.com/{repo}/compare/{prev}...{tag}")
    return "\n".join(parts).strip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default=None, help="대상 태그 (기본: 현재 HEAD 의 태그 또는 최신 태그)")
    ap.add_argument("--previous", default=None, help="비교 기준 태그 (기본: 바로 이전 태그)")
    ap.add_argument("--repo", default="progh2/catmoa")
    args = ap.parse_args()

    tag = args.tag
    if not tag:
        try:
            tag = run("describe", "--tags", "--exact-match")
        except subprocess.CalledProcessError:
            tag = run("tag", "--list", "v*", "--sort=-v:refname").splitlines()[0]
    prev = args.previous or previous_tag(tag)
    print(render(tag, prev, collect(tag, prev), args.repo), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
