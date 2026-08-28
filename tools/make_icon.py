"""앱 아이콘 생성: assets/icon.png (1024px) + icon.ico (Windows).

PyInstaller 는 Pillow 가 있으면 PNG → icns/ico 변환을 알아서 하지만, ico 는 미리 만들어 둔다.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets"


def _font(size: int):
    for name in ("/System/Library/Fonts/Apple Color Emoji.ttc", "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
                 "/System/Library/Fonts/Helvetica.ttc", "C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def make(size: int = 1024) -> Image.Image:
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    m = size // 16
    # 크림색 둥근 사각형 + 주황 테두리
    d.rounded_rectangle((m, m, size - m, size - m), radius=size // 5, fill=(255, 250, 240, 255),
                        outline=(240, 194, 123, 255), width=size // 28)
    # 귀
    ear_w = size // 5
    for cx in (size * 0.32, size * 0.68):
        d.polygon([(cx - ear_w / 2, size * 0.36), (cx, size * 0.14), (cx + ear_w / 2, size * 0.36)],
                  fill=(58, 46, 30, 255))
        d.polygon([(cx - ear_w / 3.2, size * 0.34), (cx, size * 0.20), (cx + ear_w / 3.2, size * 0.34)],
                  fill=(242, 166, 90, 255))
    # 얼굴 텍스트 (=^･ω･^=) — 유니코드 폰트 폴백
    text = "•ω•"
    f = _font(int(size * 0.30))
    bbox = d.textbbox((0, 0), text, font=f)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text(((size - tw) / 2 - bbox[0], size * 0.56 - th / 2 - bbox[1]), text, font=f, fill=(58, 46, 30, 255))
    # 수염
    for y in (size * 0.60, size * 0.66):
        d.line((size * 0.10, y, size * 0.26, y - size * 0.01), fill=(58, 46, 30, 255), width=size // 60)
        d.line((size * 0.74, y - size * 0.01, size * 0.90, y), fill=(58, 46, 30, 255), width=size // 60)
    return im


def make_from_cat(size: int = 1024) -> Image.Image | None:
    """사용자 고양이 이미지(기본 고양이)로 아이콘 생성: 크림색 둥근 사각형 위에 고양이."""
    src = next((p for p in [ROOT / "assets" / "cat-src" / "기본 고양이.png", ROOT / "assets" / "cat" / "idle_1.png"] if p.exists()), None)
    if src is None:
        return None
    cat = Image.open(src).convert("RGBA")
    bbox = cat.getchannel("A").getbbox()
    if bbox:
        cat = cat.crop(bbox)
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    m = size // 16
    d.rounded_rectangle((m, m, size - m, size - m), radius=size // 5, fill=(255, 250, 240, 255),
                        outline=(240, 194, 123, 255), width=size // 28)
    # 고양이를 캔버스의 82% 안에 맞춰 중앙 배치 (살짝 아래로)
    box = int(size * 0.82)
    scale = min(box / cat.width, box / cat.height)
    cat = cat.resize((max(1, int(cat.width * scale)), max(1, int(cat.height * scale))), Image.LANCZOS)
    x = (size - cat.width) // 2
    y = (size - cat.height) // 2 + size // 40
    im.alpha_composite(cat, (x, y))
    return im


def main() -> None:
    OUT.mkdir(exist_ok=True)
    im = make_from_cat() or make()
    im.save(OUT / "icon.png")
    im.save(OUT / "icon.ico", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    docs_icon = ROOT / "docs" / "icon.png"
    if docs_icon.parent.exists():
        im.resize((512, 512), Image.LANCZOS).save(docs_icon)   # 랜딩 페이지 로고/og:image
    print("wrote", OUT / "icon.png", OUT / "icon.ico", docs_icon)


if __name__ == "__main__":
    main()
