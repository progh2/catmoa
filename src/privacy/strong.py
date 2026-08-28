"""강력한 마스킹 — korean-pii-e5-base (ONNX int8) 내려받아 쓰기.

무거운 torch/transformers 없이 **onnxruntime + tokenizers** 만으로 돌린다.
모델 파일은 앱에 넣지 않고, 설정에서 옵션을 켤 때 GitHub 릴리스에서 내려받아
설정 폴더 `pii_model/` 에 둔다 (약 150MB). 모델은 전부 PC 안에서만 동작한다.

원본: https://huggingface.co/FrameByFrame/korean-pii-e5-base (MIT)
라벨: BIOES × {private_person, private_phone, private_email, private_address,
      private_date, private_url, account_number, personal_handle, ip_address}
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger(__name__)

# 릴리스 자산이 올라가는 곳 (태그는 모델 버전에 고정 — 앱 버전과 따로 움직인다)
ASSET_TAG = "pii-model-v1"
ASSET_REPO = "progh2/catmoa"
ASSET_BASE = f"https://github.com/{ASSET_REPO}/releases/download/{ASSET_TAG}"
FILES = ("model.onnx", "tokenizer.json", "labels.json")
MANIFEST = "manifest.json"

MAX_LEN = 256
CHUNK_CHARS, CHUNK_OVERLAP = 600, 100
MIN_SCORE = 0.35


def model_root() -> Path:
    from src import config as cfg

    env = os.environ.get("CATMOA_PII_MODEL")
    return Path(env) if env else cfg.config_dir() / "pii_model"


def is_installed() -> bool:
    root = model_root()
    return all((root / f).exists() for f in FILES)


def runtime_available() -> bool:
    """onnxruntime + tokenizers 가 이 빌드에 들어 있는가."""
    import importlib.util

    return all(importlib.util.find_spec(m) is not None for m in ("onnxruntime", "tokenizers"))


def installed_size() -> int:
    root = model_root()
    return sum((root / f).stat().st_size for f in FILES if (root / f).exists())


def remove() -> None:
    shutil.rmtree(model_root(), ignore_errors=True)
    Detector.reset()


# ---------------------------------------------------------------- 내려받기

def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(progress: Callable[[int, int], None] | None = None,
             should_stop: Callable[[], bool] | None = None, transport=None) -> Path:
    """모델 파일을 내려받아 설정 폴더에 놓는다. 반환: 모델 폴더. 실패 시 예외."""
    import httpx

    root = model_root()
    tmp = root.with_name(root.name + ".part")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {}
    try:
        with httpx.Client(follow_redirects=True, timeout=30, transport=transport) as c:
            r = c.get(f"{ASSET_BASE}/{MANIFEST}")
            if r.status_code == 200:
                manifest = r.json().get("files", {})
    except Exception as e:  # noqa: BLE001 - 매니페스트는 있으면 좋고 없어도 진행
        log.info("모델 매니페스트를 읽지 못했습니다(무시): %s", e)

    total = sum(int(v.get("size", 0)) for k, v in manifest.items() if k in FILES) or None
    done = 0
    with httpx.Client(follow_redirects=True, timeout=60, transport=transport) as c:
        for name in FILES:
            dst = tmp / name
            with c.stream("GET", f"{ASSET_BASE}/{name}") as resp:
                resp.raise_for_status()
                if total is None:
                    total = int(resp.headers.get("content-length", 0)) * len(FILES) or None
                with dst.open("wb") as f:
                    for chunk in resp.iter_bytes(1 << 18):
                        if should_stop and should_stop():
                            shutil.rmtree(tmp, ignore_errors=True)
                            raise RuntimeError("내려받기를 취소했습니다.")
                        f.write(chunk)
                        done += len(chunk)
                        if progress:
                            progress(done, total or done)
            want = manifest.get(name, {}).get("sha256")
            if want and _sha256(dst) != want:
                shutil.rmtree(tmp, ignore_errors=True)
                raise RuntimeError(f"{name} 파일이 손상되었습니다 (체크섬 불일치). 다시 시도해 주세요.")

    shutil.rmtree(root, ignore_errors=True)
    tmp.rename(root)
    Detector.reset()
    log.info("PII 모델 설치 완료: %s (%.0f MB)", root, installed_size() / 1e6)
    return root


def expected_size(transport=None) -> int:
    """설치 전에 보여줄 대략 용량 (매니페스트를 못 읽으면 추정치)."""
    import httpx

    try:
        with httpx.Client(follow_redirects=True, timeout=10, transport=transport) as c:
            r = c.get(f"{ASSET_BASE}/{MANIFEST}")
            if r.status_code == 200:
                return sum(int(v.get("size", 0)) for k, v in r.json().get("files", {}).items() if k in FILES)
    except Exception:  # noqa: BLE001
        pass
    return 150_000_000


# ---------------------------------------------------------------- 추론

_TRAILING_JOSA = ("이에요", "이라고", "입니다", "이야", "이랑", "한테", "에게", "으로", "이가", "이는",
                  "에서", "이고", "예요", "씨", "님", "이", "가", "은", "는", "을", "를", "야", "아",
                  "에", "의", "랑", "께", "고")
_DATE_END = re.compile(r".*(?:일|[0-9])", re.S)


@dataclass
class _Span:
    label: str
    start: int
    end: int
    score: float


class Detector:
    """ONNX 세션 + 토크나이저를 한 번만 만들어 재사용."""

    _inst: "Detector | None" = None
    _tried = False

    def __init__(self, root: Path):
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer

        self.np = np
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = max(1, min(4, os.cpu_count() or 1))
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.sess = ort.InferenceSession(str(root / "model.onnx"), opts, providers=["CPUExecutionProvider"])
        self.tok = Tokenizer.from_file(str(root / "tokenizer.json"))
        self.tok.enable_truncation(max_length=MAX_LEN)
        meta = json.loads((root / "labels.json").read_text(encoding="utf-8"))
        self.id2label = {int(k): v for k, v in meta["id2label"].items()}
        self.inputs = {i.name for i in self.sess.get_inputs()}

    @classmethod
    def get(cls) -> "Detector | None":
        if cls._inst is not None or cls._tried:
            return cls._inst
        cls._tried = True
        if not (is_installed() and runtime_available()):
            return None
        try:
            cls._inst = cls(model_root())
            log.info("강력한 마스킹 모델 로드 완료")
        except Exception as e:  # noqa: BLE001
            log.warning("강력한 마스킹 모델을 쓸 수 없어 규칙만 사용합니다: %s", e)
            cls._inst = None
        return cls._inst

    @classmethod
    def reset(cls) -> None:
        cls._inst, cls._tried = None, False

    # ---- 한 조각 추론
    def _piece(self, text: str, base: int) -> list[_Span]:
        np = self.np
        enc = self.tok.encode(text)
        if not enc.ids:
            return []
        ids = np.asarray([enc.ids], dtype=np.int64)
        mask = np.asarray([enc.attention_mask], dtype=np.int64)
        feed = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in self.inputs:
            feed["token_type_ids"] = np.zeros_like(ids)
        logits = self.sess.run(None, {k: v for k, v in feed.items() if k in self.inputs})[0][0]
        # softmax (최댓값만 필요하므로 안정적으로)
        z = logits - logits.max(axis=-1, keepdims=True)
        e = np.exp(z)
        probs = e / e.sum(axis=-1, keepdims=True)
        best = probs.argmax(axis=-1)

        spans: list[_Span] = []
        active: list | None = None            # [cat, start, end, score_sum, n]
        for i, lid in enumerate(best.tolist()):
            cs, ce = enc.offsets[i]
            label = self.id2label.get(int(lid), "O")
            if cs == ce or label == "O":
                if active:
                    spans.append(_Span(active[0], active[1], active[2], active[3] / active[4]))
                    active = None
                continue
            prefix, _, cat = label.partition("-")
            score = float(probs[i][lid])
            if prefix in ("B", "S") or not active or active[0] != cat:
                if active:
                    spans.append(_Span(active[0], active[1], active[2], active[3] / active[4]))
                active = [cat, cs, ce, score, 1]
            else:
                active[2] = ce
                active[3] += score
                active[4] += 1
        if active:
            spans.append(_Span(active[0], active[1], active[2], active[3] / active[4]))

        out = []
        for sp in spans:
            s, e2 = _trim(text, sp.label, sp.start, sp.end)
            if e2 > s and text[s:e2].strip() and sp.score >= MIN_SCORE:
                out.append(_Span(sp.label, base + s, base + e2, sp.score))
        return out

    def detect(self, text: str) -> list[_Span]:
        """긴 글은 겹치게 잘라 처리한다 (모델 입력 길이 제한)."""
        if not text.strip():
            return []
        out: list[_Span] = []
        start = 0
        while True:
            piece = text[start:start + CHUNK_CHARS]
            if piece.strip():
                out += self._piece(piece, start)
            if start + CHUNK_CHARS >= len(text):
                break
            start += CHUNK_CHARS - CHUNK_OVERLAP
        return out


def _trim(text: str, label: str, s: int, e: int) -> tuple[int, int]:
    """원본 usage.py 의 span 정규화 — 공백·문장부호와 뒤에 붙은 조사를 잘라낸다."""
    while s < e and text[s] in " .,\t\n()[]":
        s += 1
    while e > s and text[e - 1] in " .,\t\n()[]":
        e -= 1
    if label == "private_date":
        m = _DATE_END.match(text[s:e])
        if m and m.end() > 0:
            e = s + m.end()
    elif label in ("private_person", "personal_handle", "private_address"):
        for _ in range(2):
            seg = text[s:e]
            for j in _TRAILING_JOSA:
                if seg.endswith(j) and (e - s) - len(j) >= 2:
                    e -= len(j)
                    break
            else:
                break
    return s, e


def spans(text: str) -> list[dict[str, Any]]:
    """masker 가 쓰는 형태로. 모델이 없으면 빈 목록."""
    from src.privacy import rules
    from src.privacy.masker import MODEL_LABELS

    det = Detector.get()
    if det is None:
        return []
    try:
        found = det.detect(text)
    except Exception as e:  # noqa: BLE001
        log.info("강력한 마스킹 추론 실패(무시): %s", e)
        return []
    out = []
    for sp in found:
        label = MODEL_LABELS.get(sp.label)
        if not label:
            continue
        val = text[sp.start:sp.end]
        # 날짜는 **생년월일 맥락일 때만** 가린다 — 일정 날짜를 가리면 앱이 일을 못 한다
        if label == "birth" and not rules.BIRTH_HINT.search(text[max(0, sp.start - 20):sp.start]):
            continue
        if label in ("id", "document_id") and rules.DATE_WITH_HOUR.fullmatch(val.strip()):
            continue
        out.append({"start": sp.start, "end": sp.end, "label": label,
                    "rule": "strong_model", "prio": 2, "confidence": sp.score})
    return out


def active() -> bool:
    return Detector.get() is not None


def status_line() -> str:
    """설정 화면에 보여줄 한 줄."""
    if not runtime_available():
        return "이 빌드에는 모델 실행기(onnxruntime)가 없습니다."
    if not is_installed():
        return "아직 내려받지 않았습니다."
    return f"설치됨 — {installed_size() / 1e6:.0f} MB ({model_root()})"


if getattr(sys, "frozen", False):  # pragma: no cover - 얼린 앱에서 경로 로깅
    log.debug("PII 모델 폴더: %s", model_root())
