"""이미지 기반 고양이 표정 로더.

파일 규격 (PNG, 투명 배경, 모든 파일 같은 캔버스 크기):
    {state}.png                 단일 프레임
    {state}_1.png, {state}_2.png…  순환 애니메이션 프레임
상태: idle hover drag thinking eating happy error sleeping — idle 만 있어도 동작(없는 상태는 idle 대체)

검색 순서: 사용자 설정 폴더 `cat/` (빌드 없이 교체 가능) → 번들 `assets/cat/`.
아무것도 없으면 None → 텍스트 표정 사용.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap

from src import config as cfg
from src.ui.styles import CAT_FACES

STATES = list(CAT_FACES.keys())
DISPLAY_SCALE = 0.5          # 레티나 2x 대응: 256px 원본 → 128px 논리 크기
MAX_LOGICAL_WIDTH = 220      # 너무 큰 이미지는 이 폭으로 축소
_FRAME_RE = re.compile(r"^([a-z]+)(?:_(\d+))?\.png$", re.I)


def bundled_assets_dir() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent.parent))
    return base / "assets" / "cat"


def user_cat_dir() -> Path:
    return cfg.config_dir() / "cat"


def find_cat_dir() -> Path | None:
    for d in (user_cat_dir(), bundled_assets_dir()):
        if d.is_dir() and any(d.glob("*.png")):
            return d
    return None


@dataclass
class CatImageSet:
    frames: dict[str, list[QPixmap]] = field(default_factory=dict)   # 상태 → 프레임 픽스맵 (논리 크기)
    logical_size: tuple[int, int] = (0, 0)
    source_dir: Path | None = None

    def frames_for(self, state: str) -> list[QPixmap]:
        return self.frames.get(state) or self.frames.get("idle") or []


def load_cat_images(directory: Path | None = None, dpr: float = 2.0) -> CatImageSet | None:
    """폴더의 PNG 를 상태별 프레임으로 묶어 로드. idle 이 없으면 None."""
    d = directory or find_cat_dir()
    if d is None:
        return None
    grouped: dict[str, list[tuple[int, Path]]] = {}
    for p in d.glob("*.png"):
        m = _FRAME_RE.match(p.name)
        if not m:
            continue
        state, idx = m.group(1).lower(), int(m.group(2) or 0)
        if state in STATES:
            grouped.setdefault(state, []).append((idx, p))
    if "idle" not in grouped:
        return None

    # 캔버스 크기는 idle 첫 프레임 기준, 모든 프레임을 같은 논리 크기로 맞춘다
    first = QPixmap(str(sorted(grouped["idle"])[0][1]))
    if first.isNull():
        return None
    lw = min(int(first.width() * DISPLAY_SCALE), MAX_LOGICAL_WIDTH)
    lh = max(1, int(first.height() * lw / max(first.width(), 1)))
    out = CatImageSet(logical_size=(lw, lh), source_dir=d)
    for state, items in grouped.items():
        frames: list[QPixmap] = []
        for _, path in sorted(items):
            pm = QPixmap(str(path))
            if pm.isNull():
                continue
            scaled = pm.scaled(int(lw * dpr), int(lh * dpr), Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
            scaled.setDevicePixelRatio(dpr)
            frames.append(scaled)
        if frames:
            out.frames[state] = frames
    return out if out.frames.get("idle") else None
