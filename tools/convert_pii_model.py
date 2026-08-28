#!/usr/bin/env python3
"""FrameByFrame/korean-pii-e5-base 를 ONNX int8 로 변환한다 (개발자용, 1회).

앱에는 onnxruntime + tokenizers 만 들어가고, 무거운 torch/transformers 는 이 스크립트에서만 쓴다.
결과물(model.onnx, tokenizer.json, labels.json)을 catmoa 릴리스에 자산으로 올리면
사용자는 설정에서 '강력한 마스킹'을 켤 때 그것만 내려받는다.

    pip install "torch>=2.0" "transformers>=4.40" onnx onnxruntime huggingface_hub
    python tools/convert_pii_model.py --out dist/pii_model
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

MODEL_ID = "FrameByFrame/korean-pii-e5-base"
MAX_LEN = 256


def export_onnx(model, out: Path) -> Path:
    import torch

    raw = out / "model_fp32.onnx"
    dummy = {
        "input_ids": torch.ones(1, 16, dtype=torch.long),
        "attention_mask": torch.ones(1, 16, dtype=torch.long),
    }
    torch.onnx.export(
        model,
        (dummy["input_ids"], dummy["attention_mask"]),
        str(raw),
        input_names=["input_ids", "attention_mask"],
        output_names=["logits"],
        dynamic_axes={"input_ids": {0: "batch", 1: "seq"},
                      "attention_mask": {0: "batch", 1: "seq"},
                      "logits": {0: "batch", 1: "seq"}},
        opset_version=14,
        do_constant_folding=True,
        dynamo=False,          # dynamic_axes 를 쓰는 기존(TorchScript) 내보내기 경로
    )
    return raw


def quantize(raw: Path, out: Path) -> Path:
    from onnxruntime.quantization import QuantType, quantize_dynamic

    q = out / "model.onnx"
    quantize_dynamic(str(raw), str(q), weight_type=QuantType.QInt8)
    return q


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="dist/pii_model")
    ap.add_argument("--keep-fp32", action="store_true")
    args = ap.parse_args()

    import torch
    from huggingface_hub import hf_hub_download
    from transformers import AutoModelForTokenClassification

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    print(f"· 모델 로드: {MODEL_ID}")
    model = AutoModelForTokenClassification.from_pretrained(MODEL_ID, torch_dtype=torch.float32)
    model.eval()

    print("· ONNX 내보내기 (fp32)")
    raw = export_onnx(model, out)
    print(f"  {raw.name}: {raw.stat().st_size / 1e6:.0f} MB")

    print("· int8 동적 양자화")
    q = quantize(raw, out)
    print(f"  {q.name}: {q.stat().st_size / 1e6:.0f} MB")
    if not args.keep_fp32:
        raw.unlink()
        for extra in out.glob("model_fp32*"):      # 큰 가중치가 따로 떨어진 경우
            extra.unlink()

    print("· 토크나이저 / 라벨")
    shutil.copy(hf_hub_download(MODEL_ID, "tokenizer.json"), out / "tokenizer.json")
    (out / "labels.json").write_text(json.dumps({
        "id2label": {str(k): v for k, v in model.config.id2label.items()},
        "model_id": MODEL_ID, "max_length": MAX_LEN, "license": "MIT",
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    files = sorted(p for p in out.iterdir() if p.is_file() and p.name != "manifest.json")
    manifest = {"model_id": MODEL_ID, "license": "MIT", "max_length": MAX_LEN,
                "files": {p.name: {"size": p.stat().st_size, "sha256": sha256(p)} for p in files}}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    total = sum(f["size"] for f in manifest["files"].values())
    print(f"\n완료: {out}  (합계 {total / 1e6:.0f} MB)")
    for name, f in manifest["files"].items():
        print(f"  {name:20} {f['size'] / 1e6:8.1f} MB  {f['sha256'][:16]}…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
