"""HWP 5.0 (바이너리) 파서 — olefile + zlib 로 본문 텍스트만 추출한다.

구조 (한글 문서 파일 형식 5.0 공개 명세):
- OLE 복합 파일. `FileHeader` 스트림 256B: 서명(32) 버전(4) 속성(4: bit0 압축, bit1 암호, bit2 배포용)
- `BodyText/Section{n}` 스트림: (압축 시 raw deflate) 레코드 나열
- 레코드 헤더 4B: tag(10bit) level(10bit) size(12bit, 0xFFF면 다음 4B가 크기)
- HWPTAG_PARA_TEXT(0x43): UTF-16LE. 코드 < 32 는 제어문자
    * 1글자 제어: 0, 10(줄바꿈), 13(문단끝), 24~31
    * 8글자(16B) 제어: 나머지 (탭 9, 표/개체 11 등)
- HWPTAG_CTRL_HEADER(0x47) + HWPTAG_TABLE(0x4D) + HWPTAG_LIST_HEADER(0x48): 표 셀 구조 복원에 사용
"""
from __future__ import annotations

import logging
import struct
import zlib
from pathlib import Path

from src.parsers import ParseError

log = logging.getLogger(__name__)

HWPTAG_BEGIN = 0x10
TAG_PARA_HEADER = HWPTAG_BEGIN + 50
TAG_PARA_TEXT = HWPTAG_BEGIN + 51
TAG_CTRL_HEADER = HWPTAG_BEGIN + 55
TAG_LIST_HEADER = HWPTAG_BEGIN + 56
TAG_TABLE = HWPTAG_BEGIN + 61

_ONE_CHAR_CTRL = {0, 10, 13, 24, 25, 26, 27, 28, 29, 30, 31}
_SIGNATURE = b"HWP Document File"


def parse_hwp(path: Path) -> str:
    import olefile

    if not olefile.isOleFile(str(path)):
        raise ParseError("HWP 5.0 형식이 아닙니다 (HWP 3.0 이하 또는 다른 파일).")
    with olefile.OleFileIO(str(path)) as ole:
        if not ole.exists("FileHeader"):
            raise ParseError("HWP FileHeader가 없습니다.")
        header = ole.openstream("FileHeader").read()
        if not header.startswith(_SIGNATURE):
            raise ParseError("HWP 서명이 올바르지 않습니다.")
        flags = struct.unpack_from("<I", header, 36)[0]
        compressed = bool(flags & 0x1)
        if flags & 0x2:
            raise ParseError("암호가 걸린 HWP는 열 수 없습니다.")
        if flags & 0x4:
            raise ParseError("배포용(읽기 전용 암호화) HWP는 열 수 없습니다. 한글에서 '다른 이름으로 저장' 후 시도하세요.")

        sections = sorted(
            (e for e in ole.listdir() if len(e) == 2 and e[0] == "BodyText" and e[1].startswith("Section")),
            key=lambda e: int(e[1][7:] or 0),
        )
        if not sections:
            raise ParseError("HWP 본문(BodyText)이 없습니다.")
        lines: list[str] = []
        for entry in sections:
            data = ole.openstream(entry).read()
            if compressed:
                try:
                    data = zlib.decompress(data, -15)
                except zlib.error as e:
                    raise ParseError(f"HWP 본문 압축 해제 실패: {e}") from e
            lines.extend(_section_lines(data))
    return "\n".join(lines).strip()


# ---------------------------------------------------------------- 레코드 순회

def _records(data: bytes):
    """(tag, level, payload) 제너레이터."""
    pos, n = 0, len(data)
    while pos + 4 <= n:
        (h,) = struct.unpack_from("<I", data, pos)
        pos += 4
        tag = h & 0x3FF
        level = (h >> 10) & 0x3FF
        size = (h >> 20) & 0xFFF
        if size == 0xFFF:
            if pos + 4 > n:
                break
            (size,) = struct.unpack_from("<I", data, pos)
            pos += 4
        payload = data[pos:pos + size]
        pos += size
        yield tag, level, payload


def _para_text(payload: bytes) -> str:
    out: list[str] = []
    i, n = 0, len(payload) - 1
    while i < n:
        code = payload[i] | (payload[i + 1] << 8)
        if 0xD800 <= code <= 0xDBFF:
            # 서로게이트 쌍 (이모지 등). 짝이 없으면 버린다.
            if i + 3 < n + 1:
                low = payload[i + 2] | (payload[i + 3] << 8)
                if 0xDC00 <= low <= 0xDFFF:
                    out.append(chr(0x10000 + ((code - 0xD800) << 10) + (low - 0xDC00)))
                    i += 4
                    continue
            i += 2
        elif 0xDC00 <= code <= 0xDFFF:
            i += 2  # 짝 없는 하위 서로게이트
        elif code >= 32:
            out.append(chr(code))
            i += 2
        elif code in _ONE_CHAR_CTRL:
            if code == 10:
                out.append("\n")
            i += 2
        else:
            if code == 9:
                out.append("\t")
            i += 16  # 8글자 제어
    return "".join(out)


class _Table:
    __slots__ = ("owner_level", "cells_per_row", "cells", "cur", "expected")

    def __init__(self, owner_level: int, cells_per_row: list[int]):
        self.owner_level = owner_level
        self.cells_per_row = cells_per_row
        self.expected = sum(cells_per_row)
        self.cells: list[str] = []
        self.cur: list[str] | None = None

    def start_cell(self):
        self.close_cell()
        self.cur = []

    def close_cell(self):
        if self.cur is not None:
            self.cells.append(" ".join(s for s in self.cur if s).replace("\n", " ").strip())
            self.cur = None

    def render(self) -> list[str]:
        self.close_cell()
        rows: list[str] = []
        idx = 0
        for cnt in self.cells_per_row:
            row = self.cells[idx:idx + cnt]
            idx += cnt
            if any(row):
                rows.append("| " + " | ".join(row) + " |")
        # 셀 수 불일치 시 남은 셀도 버리지 않는다
        rest = [c for c in self.cells[idx:] if c]
        if rest:
            rows.append("| " + " | ".join(rest) + " |")
        return rows


def _section_lines(data: bytes) -> list[str]:
    lines: list[str] = []
    stack: list[_Table] = []
    para_level = 0
    pending_table_owner: int | None = None

    def emit(s: str):
        s = s.strip("\n")
        if not s.strip():
            return
        if stack and stack[-1].cur is not None:
            stack[-1].cur.append(s)
        else:
            lines.append(s)

    for tag, level, payload in _records(data):
        if tag == TAG_PARA_HEADER:
            para_level = level
            # 표 종료 판정: 표를 담은 문단과 같거나 얕은 문단이 시작되면 표 끝
            while stack and level <= stack[-1].owner_level:
                for row in stack.pop().render():
                    emit(row)  # 중첩 표면 부모 셀에, 아니면 본문에
        elif tag == TAG_PARA_TEXT:
            emit(_para_text(payload))
        elif tag == TAG_CTRL_HEADER:
            ctrl = payload[:4]
            if ctrl in (b" lbt", b"tbl "):
                pending_table_owner = para_level
        elif tag == TAG_TABLE and pending_table_owner is not None:
            try:
                rows, cols = struct.unpack_from("<HH", payload, 4)
                cells_per_row = list(struct.unpack_from(f"<{rows}H", payload, 4 + 2 + 2 + 2 + 8))
            except struct.error:
                cells_per_row = []
            if not cells_per_row or sum(cells_per_row) == 0:
                cells_per_row = [max(cols, 1)] * max(rows, 1) if rows and cols else []
            if cells_per_row:
                stack.append(_Table(pending_table_owner, cells_per_row))
            pending_table_owner = None
        elif tag == TAG_LIST_HEADER and stack:
            t = stack[-1]
            if len(t.cells) + (1 if t.cur is not None else 0) < t.expected:
                t.start_cell()
    while stack:
        lines.extend(stack.pop().render())
    return lines
