"""되돌릴 수 있는 개인정보 마스킹.

mask_text(text) → MaskResult(masked, mapping)   # "[이름1]" → "홍길동"
restore_text(text, mapping)                       # LLM 결과에 남은 토큰을 원문으로
같은 원문 값은 같은 토큰을 받는다(문서 안에서 일관성 유지 → LLM 이 사람을 구분할 수 있음).
"""
from __future__ import annotations

import logging
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.privacy import rules

log = logging.getLogger(__name__)

# label → 토큰 접두어 (한국어 — LLM 이 의미를 이해하도록)
PLACEHOLDERS = {
    "person": "이름", "phone": "전화", "email": "이메일", "address": "주소", "id": "주민번호",
    "document_id": "문서번호", "ip": "IP", "secret": "비밀값", "birth": "생년월일",
    "klass": "반", "student_number": "학번", "url": "개인링크",
}
# 모델 라벨 → 우리 라벨
MODEL_LABELS = {
    "private_person": "person", "private_address": "address", "private_phone": "phone", "phone_number": "phone",
    "private_email": "email", "account_number": "id", "resident_id": "id", "document_id": "document_id",
    "ip": "ip", "ip_address": "ip", "private_secret": "secret", "secret": "secret", "birth_date": "birth",
    "private_class": "klass", "private_student_number": "student_number", "private_url": "url", "postal_code": "address",
}
TOKEN_RE = re.compile(r"\[(" + "|".join(map(re.escape, PLACEHOLDERS.values())) + r")(\d+)\]")


@dataclass
class MaskResult:
    masked: str
    mapping: dict[str, str] = field(default_factory=dict)     # 토큰 → 원문
    spans: list[dict[str, Any]] = field(default_factory=list)
    used_model: bool = False

    @property
    def count(self) -> int:
        return len(self.spans)

    def summary(self) -> str:
        from collections import Counter

        c = Counter(PLACEHOLDERS.get(s["label"], s["label"]) for s in self.spans)
        return ", ".join(f"{k} {v}" for k, v in c.items())


# ---------------------------------------------------------------- 선택 모델 (schift-ko-pii-v6)

_MODEL: Any = None
_MODEL_TRIED = False


def model_dir() -> Path | None:
    """설정 폴더 pii_model/ 또는 번들 assets/pii_model/ 에 config.json 이 있으면 그 폴더."""
    from src import config as cfg

    cands = [cfg.config_dir() / "pii_model",
             Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent.parent)) / "assets" / "pii_model"]
    env = os.environ.get("CATMOA_PII_MODEL")
    if env:
        cands.insert(0, Path(env))
    for d in cands:
        if (d / "config.json").exists() and (d / "model.safetensors").exists():
            return d
    return None


def model_available() -> bool:
    import importlib.util

    return model_dir() is not None and importlib.util.find_spec("schift_ko_pii") is not None


def _load_model():
    global _MODEL, _MODEL_TRIED
    if _MODEL is not None or _MODEL_TRIED:
        return _MODEL
    _MODEL_TRIED = True
    d = model_dir()
    if d is None:
        return None
    try:
        import importlib

        import huggingface_hub

        def local_download(_repo_id, filename, *a, **k):
            p = d / filename
            if not p.exists():
                raise FileNotFoundError(str(p))
            return str(p)

        huggingface_hub.hf_hub_download = local_download   # 네트워크 없이 로컬 파일만
        detect = importlib.import_module("schift_ko_pii.detect")
        detect.HF_MODEL_ID = str(d)
        detect._MODEL = None
        detect._TOKENIZER = None
        try:
            import torch

            torch.set_num_threads(max(1, min(4, os.cpu_count() or 1)))
        except ImportError:
            pass
        _MODEL = importlib.import_module("schift_ko_pii")
        log.info("PII 모델 로드: %s", d)
    except Exception as e:  # noqa: BLE001
        log.warning("PII 모델을 쓸 수 없어 규칙만 사용: %s", e)
        _MODEL = None
    return _MODEL


def _model_spans(text: str) -> list[dict[str, Any]]:
    det = _load_model()
    if det is None:
        return []
    out: list[dict[str, Any]] = []
    chunk, overlap = 650, 100
    starts = [0]
    while starts[-1] + chunk < len(text):
        starts.append(starts[-1] + chunk - overlap)
    for s0 in starts:
        piece = text[s0:s0 + chunk]
        try:
            ents = det.detect(piece, postprocess=True, normalize=False, extended=True, extended_profile="contextual")
        except Exception as e:  # noqa: BLE001
            log.info("PII 모델 탐지 실패(무시): %s", e)
            return out
        for ent in ents:
            label = MODEL_LABELS.get(str(ent.get("label") or ""))
            if not label:
                continue
            a, b = s0 + int(ent["start"]), s0 + int(ent["end"])
            val = text[a:b]
            if label == "birth" and not rules.BIRTH_RE.search(text[max(0, a - 30):b + 30]):
                continue
            if label in ("id", "document_id", "birth") and rules.DATE_WITH_HOUR.fullmatch(val.strip()):
                continue
            if label == "url" and not rules.PRIVATE_URL_HINT.search(val):
                continue
            out.append({"start": a, "end": b, "label": label, "rule": "model", "prio": 2,
                        "confidence": float(ent.get("score", 0.5))})
    return out


# ---------------------------------------------------------------- 마스킹/복원

def _choose(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """겹치는 탐지는 우선순위(규칙 > 모델) → 긴 것 순으로 하나만."""
    chosen: list[dict[str, Any]] = []
    for it in sorted(items, key=lambda x: (-x.get("prio", 1), -(x["end"] - x["start"]), x["start"])):
        if any(it["start"] < o["end"] and o["start"] < it["end"] for o in chosen):
            continue
        chosen.append(it)
    return sorted(chosen, key=lambda x: x["start"])


def mask_text(text: str, use_model: bool = True) -> MaskResult:
    if not text:
        return MaskResult(masked=text)
    items = rules.all_rules(text)
    used_model = False
    if use_model:
        ms = _model_spans(text)
        used_model = bool(ms) or _MODEL is not None
        items += ms
    spans = _choose(items)
    mapping: dict[str, str] = {}
    reverse: dict[tuple[str, str], str] = {}
    counters: dict[str, int] = {}
    parts, cursor = [], 0
    for sp in spans:
        val = text[sp["start"]:sp["end"]]
        key = (sp["label"], val.strip())
        tok = reverse.get(key)
        if tok is None:
            prefix = PLACEHOLDERS.get(sp["label"], "정보")
            counters[prefix] = counters.get(prefix, 0) + 1
            tok = f"[{prefix}{counters[prefix]}]"
            reverse[key] = tok
            mapping[tok] = val
        sp["token"] = tok
        parts.append(text[cursor:sp["start"]])
        parts.append(tok)
        cursor = sp["end"]
    parts.append(text[cursor:])
    return MaskResult(masked="".join(parts), mapping=mapping, spans=spans, used_model=used_model)


def restore_text(text: str | None, mapping: dict[str, str]) -> str | None:
    """LLM 결과에 남은 [이름1] 같은 토큰을 원문으로 되돌린다."""
    if not text or not mapping:
        return text
    return TOKEN_RE.sub(lambda m: mapping.get(m.group(0), m.group(0)), text)
