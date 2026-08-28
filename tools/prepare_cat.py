"""고양이 원본 이미지(assets/cat-src/*.png, 한글 파일명) → 상태별 배포 이미지(assets/cat/{state}[_n].png).

- 모든 원본은 같은 캔버스(1254²)에 그려져 있으므로, 전체 원본의 투명 여백 합집합 bbox 로 공통 크롭 → 프레임 간 위치 흔들림 없음
- 정사각 캔버스로 패딩 후 SIZE px 로 축소 (LANCZOS)
- 매핑은 MAPPING 참고. 같은 원본을 여러 상태/프레임에 재사용한다.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "assets" / "cat-src"
OUT = ROOT / "assets" / "cat"
SIZE = 320
MARGIN = 0.03   # 캔버스 여백 비율

# 상태 파일명 → 원본 파일명 (부분 일치, 공백 무시)
MAPPING: dict[str, str] = {
    "idle_1": "기본고양이", "idle_2": "기본고양이", "idle_3": "기본고양이", "idle_4": "기본고양이",
    "idle_5": "기본고양이", "idle_6": "눈감는고양이",          # 6프레임 중 1프레임 깜빡임
    "hover": "기쁜고양이",
    "drag": "놀란고양이",
    "thinking": "서류찾는고양이",
    "searching": "서류찾는고양이",
    "eating_1": "밥먹는고양이1", "eating_2": "밥먹는고양이2",
    "happy": "기쁜고양이",
    "error": "우는고양이",
    "annoyed": "화난고양이",
    "empty": "시무룩한고양이",
    "bored": "지루해하는고양이",
    "sleeping": "눈감는고양이",
}


# 선택 매핑: 원본이 있을 때만 생성. 여러 후보 표기를 허용 (마우스 방향을 쳐다보는 호버)
OPTIONAL: dict[str, list[str]] = {
    "hover_tl": ["왼쪽위", "좌상", "왼쪽 위", "topleft", "top_left", "tl"],
    "hover_tr": ["오른쪽위", "우상", "오른쪽 위", "topright", "top_right", "tr"],
    "hover_bl": ["왼쪽아래", "아래왼", "좌하", "왼쪽 아래", "bottomleft", "bottom_left", "bl"],
    "hover_br": ["오른쪽아래", "아래오른", "우하", "오른쪽 아래", "bottomright", "bottom_right", "br"],
}


def _key(name: str) -> str:
    return "".join(name.split()).lower()


def find_src(label: str) -> Path:
    want = _key(label)
    for p in SRC.glob("*.png"):
        if want in _key(p.stem):
            return p
    raise FileNotFoundError(f"원본을 찾을 수 없음: {label}")


def find_optional(labels: list[str]) -> Path | None:
    for label in labels:
        try:
            return find_src(label)
        except FileNotFoundError:
            continue
    return None


def union_bbox(paths: list[Path]) -> tuple[int, int, int, int]:
    box = None
    for p in paths:
        a = Image.open(p).convert("RGBA").getchannel("A")
        b = a.getbbox()
        if b is None:
            continue
        box = b if box is None else (min(box[0], b[0]), min(box[1], b[1]), max(box[2], b[2]), max(box[3], b[3]))
    if box is None:
        raise RuntimeError("모든 원본이 비어 있음")
    # 정사각으로 확장
    w, h = box[2] - box[0], box[3] - box[1]
    side = max(w, h)
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    half = side / 2 * (1 + MARGIN)
    return int(cx - half), int(cy - half), int(cx + half), int(cy + half)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    srcs = {state: find_src(label) for state, label in MAPPING.items()}
    for state, labels in OPTIONAL.items():
        p = find_optional(labels)
        if p is not None:
            srcs[state] = p
        else:
            print(f"(선택) {state}: 원본 없음 — 건너뜀")
    box = union_bbox(sorted(set(srcs.values())))
    cache: dict[Path, Image.Image] = {}
    for state, src in srcs.items():
        if src not in cache:
            im = Image.open(src).convert("RGBA")
            canvas = Image.new("RGBA", (box[2] - box[0], box[3] - box[1]), (0, 0, 0, 0))
            # 크롭 영역이 원본 밖으로 나가면 투명으로 채움
            canvas.paste(im.crop(box), (0, 0))
            cache[src] = canvas.resize((SIZE, SIZE), Image.LANCZOS)
        out = OUT / f"{state}.png"
        cache[src].save(out, optimize=True)
        print(f"{out.name:14s} ← {src.name}  {out.stat().st_size // 1024}KB")
    print(f"crop box {box}, {len(srcs)} files → {OUT}")


if __name__ == "__main__":
    main()
