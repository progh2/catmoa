"""LLM 공급자 실검증 (개발용).

    python tools/check_llm.py gemini  --key AIza...
    python tools/check_llm.py upstage --key up_...
    python tools/check_llm.py ollama  --model gemma4:latest
키를 생략하면 keyring(설정에서 저장한 키)을 사용한다. 모델을 생략하면 목록의 첫 모델.
모델 목록 → 연결 테스트 → 텍스트 일정 추출 → 이미지(비전/OCR) 일정 추출 순으로 확인한다.
"""
from __future__ import annotations

import argparse
import io
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.extract import Extractor  # noqa: E402
from src.llm import PROVIDERS, create_provider  # noqa: E402
from src.parsers import ParsedInput  # noqa: E402


def sample_image() -> bytes:
    from PIL import Image, ImageDraw, ImageFont

    im = Image.new("RGB", (640, 160), "white")
    d = ImageDraw.Draw(im)
    try:
        f = ImageFont.truetype("/System/Library/Fonts/Supplemental/AppleGothic.ttf", 28)
    except OSError:
        f = ImageFont.load_default()
    d.text((20, 30), "학부모 상담 주간: 9월 15일(월) 14:00 ~ 16:00", font=f, fill="black")
    d.text((20, 80), "상담 신청서 9월 10일까지 제출", font=f, fill="black")
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("provider", choices=list(PROVIDERS))
    ap.add_argument("--key")
    ap.add_argument("--model")
    ap.add_argument("--no-image", action="store_true")
    a = ap.parse_args()

    p = create_provider(provider=a.provider, model=a.model or "", api_key=a.key)
    t0 = time.time()
    models = p.list_models()
    print(f"[{a.provider}] 모델 {len(models)}개 ({time.time() - t0:.1f}s):", [f"{m.id}{'👁' if m.vision else ''}" for m in models[:12]])
    if not a.model:
        p.model = models[0].id if models else p.model
    print("사용 모델:", p.model)
    r = p.check()
    print("연결 테스트:", "✅" if r.ok else "❌", r.message)
    if not r.ok:
        return 1

    ex = Extractor(p)
    ref = date(2026, 8, 28)
    t0 = time.time()
    res = ex.extract(ParsedInput(text="다음 주 화요일 오후 2시 교무회의(회의실). 9/12까지 방과후 계획서 제출."), ref)
    print(f"텍스트 추출 ({time.time() - t0:.1f}s):")
    for it in res.items:
        print(f"   [{it.kind}] {it.describe_when()}  {it.title}")
    if not a.no_image:
        t0 = time.time()
        res = ex.extract(ParsedInput(images=[sample_image()]), ref)
        print(f"이미지 추출 ({time.time() - t0:.1f}s):")
        for it in res.items:
            print(f"   [{it.kind}] {it.describe_when()}  {it.title}")
        for w in res.warnings:
            print("   ⚠", w)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
