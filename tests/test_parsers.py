import io
import os
import zipfile
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from src.parsers import ParseError, is_supported, normalize_image, parse_file
from src.parsers.hwp import _para_text
from src.parsers.hwpx import parse_hwpx

FIX = Path(__file__).parent / "_tmp"


@pytest.fixture(autouse=True)
def _fixdir():
    FIX.mkdir(exist_ok=True)
    yield


# ---------------------------------------------------------------- 공통

def test_is_supported():
    assert is_supported("a.HWP") and is_supported("b.pdf") and is_supported("c.png")
    assert not is_supported("d.docx")


def test_unsupported_and_missing(tmp_path):
    f = tmp_path / "x.docx"
    f.write_bytes(b"x")
    with pytest.raises(ParseError):
        parse_file(f)
    with pytest.raises(ParseError):
        parse_file(tmp_path / "nope.pdf")


def test_text_file_cp949(tmp_path):
    f = tmp_path / "memo.txt"
    f.write_bytes("내일 3시 회의".encode("cp949"))
    assert parse_file(f).text == "내일 3시 회의"


def test_image_file_normalized(tmp_path):
    im = Image.new("RGB", (3000, 100), "white")
    f = tmp_path / "shot.jpg"
    im.save(f, "JPEG")
    r = parse_file(f)
    assert len(r.images) == 1
    out = Image.open(io.BytesIO(r.images[0]))
    assert out.format == "PNG" and max(out.size) == 2000


# ---------------------------------------------------------------- HWPX

HWPX_NS = 'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"'


def _make_hwpx(path: Path, section_xml: str):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/hwp+zip")
        z.writestr("Contents/section0.xml", f'<?xml version="1.0" encoding="UTF-8"?><hs:sec {HWPX_NS}>{section_xml}</hs:sec>')


def test_hwpx_paragraphs_and_table(tmp_path):
    xml = (
        "<hp:p><hp:run><hp:t>2026학년도 연수 안내</hp:t></hp:run></hp:p>"
        "<hp:p><hp:run><hp:t>일시: 9월 3일<hp:lineBreak/>14:00</hp:t></hp:run></hp:p>"
        "<hp:p><hp:run><hp:tbl>"
        "<hp:tr><hp:tc><hp:subList><hp:p><hp:run><hp:t>구분</hp:t></hp:run></hp:p></hp:subList></hp:tc>"
        "<hp:tc><hp:subList><hp:p><hp:run><hp:t>날짜</hp:t></hp:run></hp:p></hp:subList></hp:tc></hp:tr>"
        "<hp:tr><hp:tc><hp:subList><hp:p><hp:run><hp:t>제출</hp:t></hp:run></hp:p></hp:subList></hp:tc>"
        "<hp:tc><hp:subList><hp:p><hp:run><hp:t>9/10</hp:t></hp:run></hp:p></hp:subList></hp:tc></hp:tr>"
        "</hp:tbl></hp:run></hp:p>"
        "<hp:p><hp:run><hp:t>끝.</hp:t></hp:run></hp:p>"
    )
    f = tmp_path / "t.hwpx"
    _make_hwpx(f, xml)
    text = parse_hwpx(f)
    assert text.splitlines() == [
        "2026학년도 연수 안내", "일시: 9월 3일", "14:00",
        "| 구분 | 날짜 |", "| 제출 | 9/10 |", "끝.",
    ]


def test_hwpx_bad_zip(tmp_path):
    f = tmp_path / "bad.hwpx"
    f.write_bytes(b"not a zip")
    with pytest.raises(ParseError):
        parse_file(f)


# ---------------------------------------------------------------- HWP

def test_hwp_para_text_controls():
    # "AB" + 탭(8글자 제어) + "C" + 줄바꿈(10) + 문단끝(13) + 서로게이트 쌍(😀) + 짝없는 서로게이트
    payload = b"".join([
        "A".encode("utf-16-le"), "B".encode("utf-16-le"),
        (9).to_bytes(2, "little") + b"\x00" * 14,
        "C".encode("utf-16-le"),
        (10).to_bytes(2, "little"), (13).to_bytes(2, "little"),
        "😀".encode("utf-16-le"),
        (0xD83D).to_bytes(2, "little"),
    ])
    assert _para_text(payload) == "AB\tC\n😀"


def test_hwp_not_ole(tmp_path):
    f = tmp_path / "x.hwp"
    f.write_bytes(b"HWP Document File V3")
    with pytest.raises(ParseError):
        parse_file(f)


@pytest.mark.skipif(not os.environ.get("CATMOA_SAMPLE_HWP"), reason="CATMOA_SAMPLE_HWP 미지정")
def test_hwp_real_sample():
    r = parse_file(os.environ["CATMOA_SAMPLE_HWP"])
    assert len(r.text) > 50
    r.text.encode("utf-8")  # 서로게이트 없음


# ---------------------------------------------------------------- PDF

def _make_text_pdf(path: Path, text: str):
    """최소 텍스트 PDF (ASCII, Helvetica) — 외부 의존 없이 손으로 작성."""
    stream = f"BT /F1 18 Tf 50 700 Td ({text}) Tj ET".encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(bytes(out))


def test_pdf_text(tmp_path):
    f = tmp_path / "t.pdf"
    _make_text_pdf(f, "Meeting on 2026-09-03 at 14:00 in Room 301")
    r = parse_file(f)
    assert "2026-09-03" in r.text and r.images == []


def test_pdf_scanned_renders_images(tmp_path):
    im = Image.new("RGB", (600, 800), "white")
    ImageDraw.Draw(im).text((50, 50), "scan", fill="black")
    f = tmp_path / "scan.pdf"
    im.save(f, "PDF")
    r = parse_file(f)
    assert r.text == "" and len(r.images) == 1
    assert Image.open(io.BytesIO(r.images[0])).format == "PNG"


def test_normalize_image_bad():
    with pytest.raises(ParseError):
        normalize_image(b"garbage")
