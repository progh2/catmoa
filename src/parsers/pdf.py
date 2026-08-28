"""PDF 파서: 텍스트 레이어 추출, 텍스트가 없는(스캔) 페이지는 이미지로 렌더."""
from __future__ import annotations

import io
import logging
from pathlib import Path

from src.parsers import ParsedInput, ParseError

log = logging.getLogger(__name__)

MIN_TEXT_CHARS_PER_PAGE = 20   # 이보다 적으면 스캔 페이지로 간주
MAX_IMAGE_PAGES = 10           # 비전 LLM에 보낼 최대 페이지 수
RENDER_SCALE = 1.5             # 72dpi × 1.5 ≈ 108dpi (한글 공문 가독 충분, 용량 절약)


def parse_pdf(path: Path) -> ParsedInput:
    import pdfplumber

    texts: list[str] = []
    scan_pages: list[int] = []
    try:
        with pdfplumber.open(str(path)) as pdf:
            for i, page in enumerate(pdf.pages):
                try:
                    t = page.extract_text() or ""
                except Exception as e:  # noqa: BLE001 - 페이지 단위 손상 허용
                    log.warning("PDF %s p%d 텍스트 추출 실패: %s", path.name, i + 1, e)
                    t = ""
                if len(t.strip()) < MIN_TEXT_CHARS_PER_PAGE:
                    scan_pages.append(i)
                else:
                    texts.append(f"[p.{i + 1}]\n{t.strip()}")
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        if "password" in msg.lower() or "encrypt" in msg.lower():
            raise ParseError("암호가 걸린 PDF는 열 수 없습니다.") from e
        raise ParseError(f"PDF를 열 수 없습니다: {e}") from e

    images = _render_pages(path, scan_pages[:MAX_IMAGE_PAGES]) if scan_pages else []
    if len(scan_pages) > MAX_IMAGE_PAGES:
        log.info("PDF %s: 스캔 페이지 %d개 중 앞 %d개만 사용", path.name, len(scan_pages), MAX_IMAGE_PAGES)
    return ParsedInput(text="\n\n".join(texts), images=images)


def _render_pages(path: Path, page_indices: list[int]) -> list[bytes]:
    import pypdfium2 as pdfium

    out: list[bytes] = []
    try:
        doc = pdfium.PdfDocument(str(path))
    except Exception as e:  # noqa: BLE001
        raise ParseError(f"PDF 렌더링 실패: {e}") from e
    try:
        for i in page_indices:
            page = doc[i]
            bitmap = page.render(scale=RENDER_SCALE)
            pil = bitmap.to_pil()
            buf = io.BytesIO()
            pil.convert("RGB").save(buf, "PNG", optimize=True)
            out.append(buf.getvalue())
            page.close()
    finally:
        doc.close()
    return out
