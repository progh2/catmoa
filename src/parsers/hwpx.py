"""HWPX 파서 (OWPML). zip 안의 Contents/section*.xml 을 stdlib만으로 파싱한다.

구조: <hp:p> 문단 > <hp:run> > <hp:t> 텍스트
표:   <hp:tbl> > <hp:tr> > <hp:tc> > <hp:subList> > <hp:p> ...
표는 "| a | b |" 형태의 줄로 렌더해 LLM이 행 구조를 알 수 있게 한다.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from src.parsers import ParseError

_SECTION_RE = re.compile(r"^Contents/section(\d+)\.xml$", re.I)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_hwpx(path: Path) -> str:
    try:
        zf = zipfile.ZipFile(path)
    except zipfile.BadZipFile as e:
        raise ParseError("HWPX 파일이 손상되었거나 형식이 아닙니다.") from e
    with zf:
        sections = sorted(
            ((int(m.group(1)), n) for n in zf.namelist() if (m := _SECTION_RE.match(n))),
            key=lambda x: x[0],
        )
        if not sections:
            raise ParseError("HWPX에 본문(section)이 없습니다.")
        lines: list[str] = []
        for _, name in sections:
            try:
                root = ET.fromstring(zf.read(name))
            except ET.ParseError as e:
                raise ParseError(f"HWPX XML 파싱 실패 ({name}): {e}") from e
            for child in root:
                if _local(child.tag) == "p":
                    lines.extend(_para_lines(child))
    text = "\n".join(l for l in lines if l is not None)
    return _tidy(text)


def _para_lines(p: ET.Element) -> list[str]:
    """문단 하나 → 줄 목록. 문단 안에 표가 있으면 표 줄들이 끼어든다."""
    lines: list[str] = []
    buf: list[str] = []

    def flush():
        s = "".join(buf).strip()
        if s:
            lines.append(s)
        buf.clear()

    for run in p:
        lt = _local(run.tag)
        if lt != "run":
            continue
        for el in run:
            k = _local(el.tag)
            if k == "t":
                buf.append(_t_text(el))
            elif k == "tbl":
                flush()
                lines.extend(_table_lines(el))
            elif k in ("secPr", "ctrl", "pic", "container", "equation", "line", "rect", "ellipse"):
                # 도형/컨테이너 안의 텍스트 (텍스트 상자 등)
                inner = _nested_text(el)
                if inner:
                    flush()
                    lines.extend(inner)
    flush()
    return lines


def _t_text(t: ET.Element) -> str:
    """<hp:t> 안의 텍스트 + 줄바꿈/탭 등 인라인 요소 처리."""
    parts = [t.text or ""]
    for c in t:
        k = _local(c.tag)
        if k == "lineBreak":
            parts.append("\n")
        elif k == "tab":
            parts.append("\t")
        elif k in ("fwSpace", "nbSpace"):
            parts.append(" ")
        parts.append(c.tail or "")
    return "".join(parts)


def _table_lines(tbl: ET.Element) -> list[str]:
    rows: list[list[str]] = []
    for tr in tbl:
        if _local(tr.tag) != "tr":
            continue
        cells: list[str] = []
        for tc in tr:
            if _local(tc.tag) != "tc":
                continue
            cell_lines: list[str] = []
            for sub in tc:
                if _local(sub.tag) == "subList":
                    for p in sub:
                        if _local(p.tag) == "p":
                            cell_lines.extend(_para_lines(p))
            cells.append(" ".join(cell_lines).replace("\n", " ").strip())
        rows.append(cells)
    if not rows:
        return []
    return ["| " + " | ".join(c for c in r) + " |" for r in rows if any(r)]


def _nested_text(el: ET.Element) -> list[str]:
    """텍스트 상자 등 컨테이너 안의 subList/p 텍스트."""
    out: list[str] = []
    for sub in el.iter():
        if _local(sub.tag) == "subList":
            for p in sub:
                if _local(p.tag) == "p":
                    out.extend(_para_lines(p))
            break  # 가장 바깥 subList만 (안쪽은 재귀로 처리됨)
    return out


def _tidy(text: str) -> str:
    text = text.replace("\r", "")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
