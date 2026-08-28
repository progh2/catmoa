"""문서 파서: 파일/바이트 → ParsedInput(text, images).

지원: .pdf .hwpx .hwp / 이미지(.png .jpg .jpeg .gif .webp .bmp) / .txt .md
모두 순수 Python wheel만 사용한다 (외부 바이너리 없음 — 3-OS PyInstaller 빌드 조건).
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path


class ParseError(Exception):
    """사용자에게 보여줄 파싱 오류."""


@dataclass
class ParsedInput:
    text: str = ""
    images: list[bytes] = field(default_factory=list)   # PNG 바이트
    source: str = ""                                     # 표시용 파일명

    @property
    def is_empty(self) -> bool:
        return not self.text.strip() and not self.images


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
TEXT_EXTS = {".txt", ".md", ".csv"}
DOC_EXTS = {".pdf", ".hwpx", ".hwp"}
SUPPORTED_EXTS = IMAGE_EXTS | TEXT_EXTS | DOC_EXTS


def is_supported(path: str | Path) -> bool:
    return Path(path).suffix.lower() in SUPPORTED_EXTS


def parse_file(path: str | Path) -> ParsedInput:
    p = Path(path)
    if not p.exists():
        raise ParseError(f"파일이 없습니다: {p}")
    ext = p.suffix.lower()
    if ext == ".pdf":
        from src.parsers.pdf import parse_pdf

        r = parse_pdf(p)
    elif ext == ".hwpx":
        from src.parsers.hwpx import parse_hwpx

        r = ParsedInput(text=parse_hwpx(p))
    elif ext == ".hwp":
        from src.parsers.hwp import parse_hwp

        r = ParsedInput(text=parse_hwp(p))
    elif ext in IMAGE_EXTS:
        r = ParsedInput(images=[normalize_image(p.read_bytes())])
    elif ext in TEXT_EXTS:
        r = ParsedInput(text=_read_text(p))
    else:
        raise ParseError(f"지원하지 않는 형식입니다: {ext or '(확장자 없음)'}")
    r.source = p.name
    if r.is_empty:
        raise ParseError(f"내용을 읽을 수 없습니다: {p.name}")
    return r


def normalize_image(data: bytes) -> bytes:
    """어떤 이미지든 PNG로 통일 (LLM 공급자 호환성)."""
    from PIL import Image

    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except Exception as e:  # noqa: BLE001
        raise ParseError(f"이미지를 열 수 없습니다: {e}") from e
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGB")
    # 지나치게 큰 이미지는 축소 (긴 변 2000px)
    m = max(im.size)
    if m > 2000:
        s = 2000 / m
        im = im.resize((int(im.width * s), int(im.height * s)))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def _read_text(p: Path) -> str:
    for enc in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            return p.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    return p.read_text(encoding="utf-8", errors="replace")
