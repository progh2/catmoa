"""중복 확인 다이얼로그 — 등록하려는 항목과 비슷한 기존 캘린더/태스크 항목을 보여주고 처리 방법을 고른다."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from src.gsync.dedupe import DupMatch

CHOICES = [("skip", "건너뛰기 (등록 안 함)"), ("update", "기존 항목 갱신 (일시·메모 덮어쓰기)"), ("create", "그래도 새로 등록")]
TARGET_ICON = {"calendar": "📅", "task": "✅"}


class DedupeDialog(QDialog):
    def __init__(self, matches: list[DupMatch], parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("비슷한 항목이 이미 있어요")
        self.setMinimumWidth(720)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.matches = matches
        self.combos: list[QComboBox] = []

        lay = QVBoxLayout(self)
        head = QLabel(f"<b>{len(matches)}개</b> 항목이 이미 등록된 것과 비슷합니다. 각각 어떻게 할지 고르세요.")
        head.setWordWrap(True)
        lay.addWidget(head)

        bulk = QHBoxLayout()
        for label, key in (("모두 건너뛰기", "skip"), ("모두 갱신", "update"), ("모두 새로 등록", "create")):
            b = QPushButton(label)
            b.clicked.connect(lambda _, k=key: self._bulk(k))
            bulk.addWidget(b)
        bulk.addStretch(1)
        lay.addLayout(bulk)

        body = QWidget()
        grid = QGridLayout(body)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)
        grid.addWidget(QLabel("<b>새 항목</b>"), 0, 1)
        grid.addWidget(QLabel("<b>기존 항목</b>"), 0, 2)
        grid.addWidget(QLabel("<b>처리</b>"), 0, 3)
        for i, m in enumerate(matches, 1):
            icon = QLabel(TARGET_ICON.get(m.target, ""))
            new = QLabel(f"{m.decision.item.title}<br><span style='color:gray'>{m.decision.item.describe_when()}</span>")
            new.setTextFormat(Qt.TextFormat.RichText)
            new.setWordWrap(True)
            old_txt = f"{m.title}<br><span style='color:gray'>{m.when} · 유사도 {int(m.score * 100)}%</span>"
            if m.link:
                old_txt += f" <a href='{m.link}'>열기</a>"
            old = QLabel(old_txt)
            old.setTextFormat(Qt.TextFormat.RichText)
            old.setOpenExternalLinks(True)
            old.setWordWrap(True)
            combo = QComboBox()
            for key, label in CHOICES:
                combo.addItem(label, key)
            combo.setCurrentIndex(0)
            self.combos.append(combo)
            grid.addWidget(icon, i, 0)
            grid.addWidget(new, i, 1)
            grid.addWidget(old, i, 2)
            grid.addWidget(combo, i, 3)
            line = QFrame()
            line.setFrameShape(QFrame.Shape.HLine)
            grid.addWidget(line, i, 0, 1, 4, Qt.AlignmentFlag.AlignBottom)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        lay.addWidget(scroll, 1)

        foot = QHBoxLayout()
        foot.addStretch(1)
        cancel = QPushButton("등록 취소")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("계속")
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        foot.addWidget(cancel)
        foot.addWidget(ok)
        lay.addLayout(foot)

    def _bulk(self, key: str):
        for c in self.combos:
            c.setCurrentIndex([k for k, _ in CHOICES].index(key))

    def choices(self) -> list[str]:
        return [c.currentData() for c in self.combos]
