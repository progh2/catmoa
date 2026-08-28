"""통합 큐에 들어가는 입력 단위."""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Literal

InputKind = Literal["file", "text", "image", "coolm", "inbox_task"]

_seq = itertools.count(1)


@dataclass
class InputItem:
    kind: InputKind
    payload: Any                              # Path | str | bytes
    source_label: str = ""                    # UI 표시용 ("공문.hwp", "쿨메신저: 홍길동", "클립보드 이미지")
    reference_date: date = field(default_factory=date.today)   # 상대 날짜 기준일
    origin_ref: str | None = None             # inbox 태스크 id, 쿨메신저 MessageKey 등 후처리용
    extra: dict = field(default_factory=dict)
    id: int = field(default_factory=lambda: next(_seq))

    def __post_init__(self):
        if not self.source_label:
            if self.kind == "file":
                self.source_label = Path(self.payload).name
            elif self.kind == "image":
                self.source_label = "이미지"
            elif self.kind == "text":
                s = str(self.payload).strip().splitlines()[0] if str(self.payload).strip() else "텍스트"
                self.source_label = s[:30] + ("…" if len(s) > 30 else "")

    @property
    def short(self) -> str:
        return self.source_label or f"{self.kind}#{self.id}"
