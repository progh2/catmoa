"""일정 검토 다이얼로그.

추출된 항목을 행 단위로 보여주고, 항목별로 캘린더⇄태스크 전환·알람·내용 편집을 한 뒤
[등록]을 누르면 Decision 목록을 돌려준다.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time

from PySide6.QtCore import QDate, Qt, QTime, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QScrollArea, QSpinBox, QTimeEdit, QVBoxLayout, QWidget,
)

from src import config as cfg
from src.extract.schema import ScheduleItem

TARGET_LABELS = {"calendar": "📅 캘린더", "task": "✅ 태스크"}


@dataclass
class Decision:
    item: ScheduleItem
    target: str                 # "calendar" | "task"
    alarm_minutes: int | None   # None = 알람 없음


class _Row(QFrame):
    def __init__(self, item: ScheduleItem, settings: cfg.ScheduleSettings, parent=None):
        super().__init__(parent)
        self.item = item
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("_Row { background: palette(base); border: 1px solid palette(mid); border-radius: 8px; }")

        # ---- 1행: 선택 · 대상 · 제목 · 알람
        self.check = QCheckBox()
        self.check.setChecked(True)
        self.target = QComboBox()
        for key, label in TARGET_LABELS.items():
            self.target.addItem(label, key)
        if settings.default_target == "auto":
            default = "calendar" if item.kind == "event" else "task"
        else:
            default = settings.default_target
        self.target.setCurrentIndex(0 if default == "calendar" else 1)
        self.title = QLineEdit(item.title)
        self.title.setPlaceholderText("제목")
        self.alarm = QCheckBox("알람")
        self.alarm.setChecked(settings.alarm_enabled)
        self.alarm_min = QSpinBox()
        self.alarm_min.setRange(0, 7 * 24 * 60)
        self.alarm_min.setSuffix("분 전")
        self.alarm_min.setValue(item.alarm_minutes if item.alarm_minutes is not None else settings.alarm_minutes)
        self.alarm.toggled.connect(self.alarm_min.setEnabled)
        self.alarm_min.setEnabled(self.alarm.isChecked())

        r1 = QHBoxLayout()
        r1.addWidget(self.check)
        r1.addWidget(self.target)
        r1.addWidget(self.title, 1)
        r1.addWidget(self.alarm)
        r1.addWidget(self.alarm_min)

        # ---- 2행: 날짜 · 종일 · 시간 ~ 종료 · 장소
        self.date = QDateEdit(QDate(item.start.year, item.start.month, item.start.day))
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("yyyy-MM-dd (ddd)")
        self.all_day = QCheckBox("종일")
        self.all_day.setChecked(item.all_day)
        self.time = QTimeEdit(QTime(item.start.hour, item.start.minute))
        self.time.setDisplayFormat("HH:mm")
        end = item.end
        self.end_time = QTimeEdit(QTime(end.hour, end.minute) if end and not item.all_day else QTime(item.start.hour + 1 if item.start.hour < 23 else 23, item.start.minute))
        self.end_time.setDisplayFormat("HH:mm")
        self.has_end = QCheckBox("종료")
        self.has_end.setChecked(bool(end))
        self.end_date = QDateEdit(QDate(end.year, end.month, end.day) if end else self.date.date())
        self.end_date.setCalendarPopup(True)
        self.end_date.setDisplayFormat("yyyy-MM-dd")
        self.location = QLineEdit(item.location or "")
        self.location.setPlaceholderText("장소")

        r2 = QHBoxLayout()
        r2.addSpacing(24)
        r2.addWidget(self.date)
        r2.addWidget(self.all_day)
        r2.addWidget(self.time)
        r2.addWidget(self.has_end)
        r2.addWidget(self.end_date)
        r2.addWidget(self.end_time)
        r2.addWidget(self.location, 1)

        # ---- 3행: 근거/메모 (작게)
        self.notes = QLabel()
        self.notes.setStyleSheet("color: palette(mid); font-size: 11px;")
        self.notes.setWordWrap(True)
        meta = []
        if item.source:
            meta.append(item.source)
        meta.append(f"확신 {int(item.confidence * 100)}%")
        if item.notes:
            meta.append(item.notes)
        self.notes.setText(" · ".join(meta))

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(4)
        lay.addLayout(r1)
        lay.addLayout(r2)
        lay.addWidget(self.notes)

        self.all_day.toggled.connect(self._sync_enabled)
        self.has_end.toggled.connect(self._sync_enabled)
        self.check.toggled.connect(self._sync_enabled)
        self.target.currentIndexChanged.connect(self._sync_enabled)
        self._sync_enabled()

    def _sync_enabled(self, *_):
        on = self.check.isChecked()
        for w in (self.target, self.title, self.alarm, self.date, self.all_day, self.time,
                  self.has_end, self.end_date, self.end_time, self.location):
            w.setEnabled(on)
        if on:
            self.alarm_min.setEnabled(self.alarm.isChecked())
            all_day = self.all_day.isChecked()
            self.time.setEnabled(not all_day)
            self.end_time.setEnabled(self.has_end.isChecked() and not all_day)
            self.end_date.setEnabled(self.has_end.isChecked())
        else:
            self.alarm_min.setEnabled(False)

    def set_target(self, key: str):
        self.target.setCurrentIndex(0 if key == "calendar" else 1)

    def decision(self) -> Decision | None:
        if not self.check.isChecked():
            return None
        d = self.date.date()
        all_day = self.all_day.isChecked()
        t = self.time.time()
        start = datetime(d.year(), d.month(), d.day(), 0 if all_day else t.hour(), 0 if all_day else t.minute())
        end = None
        if self.has_end.isChecked():
            ed = self.end_date.date()
            et = self.end_time.time()
            end = datetime(ed.year(), ed.month(), ed.day(), 0 if all_day else et.hour(), 0 if all_day else et.minute())
            if end < start:
                end = None
        item = self.item.model_copy(update={
            "title": self.title.text().strip() or self.item.title,
            "start": start, "end": end, "all_day": all_day,
            "kind": self.target.currentData(),
            "location": self.location.text().strip() or None,
            "alarm_minutes": self.alarm_min.value() if self.alarm.isChecked() else None,
        })
        return Decision(item=item, target=self.target.currentData(),
                        alarm_minutes=self.alarm_min.value() if self.alarm.isChecked() else None)


class ReviewDialog(QDialog):
    submitted = Signal(list)   # list[Decision]

    def __init__(self, items: list[ScheduleItem], settings: cfg.ScheduleSettings, *,
                 source_label: str = "", warnings: list[str] | None = None,
                 preview_text: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(f"일정 검토 — {source_label}" if source_label else "일정 검토")
        self.setMinimumWidth(760)
        self.resize(820, min(160 + 130 * max(len(items), 1), 720))
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

        head = QLabel(f"<b>{len(items)}개</b>의 일정을 찾았습니다. 확인 후 등록하세요." if items
                      else "일정을 찾지 못했습니다.")
        lay = QVBoxLayout(self)
        lay.addWidget(head)
        for w in warnings or []:
            wl = QLabel(f"⚠ {w}")
            wl.setStyleSheet("color: #b8860b;")
            lay.addWidget(wl)

        # 일괄 버튼
        bulk = QHBoxLayout()
        for label, fn in (("모두 📅 캘린더", lambda: self._bulk_target("calendar")),
                          ("모두 ✅ 태스크", lambda: self._bulk_target("task")),
                          ("모두 선택", lambda: self._bulk_check(True)),
                          ("모두 해제", lambda: self._bulk_check(False))):
            b = QPushButton(label)
            b.clicked.connect(fn)
            bulk.addWidget(b)
        bulk.addStretch(1)
        lay.addLayout(bulk)

        # 행 목록
        self.rows: list[_Row] = []
        body = QWidget()
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(0, 0, 0, 0)
        for it in items:
            row = _Row(it, settings)
            self.rows.append(row)
            body_lay.addWidget(row)
        body_lay.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        lay.addWidget(scroll, 1)

        # 원본 미리보기
        if preview_text:
            self.preview_btn = QPushButton("원본 보기 ▾")
            self.preview_btn.setCheckable(True)
            self.preview = QPlainTextEdit(preview_text[:4000])
            self.preview.setReadOnly(True)
            self.preview.setMaximumHeight(160)
            self.preview.hide()
            self.preview_btn.toggled.connect(self.preview.setVisible)
            lay.addWidget(self.preview_btn)
            lay.addWidget(self.preview)

        # 하단
        foot = QHBoxLayout()
        foot.addStretch(1)
        cancel = QPushButton("취소")
        cancel.clicked.connect(self.reject)
        self.ok = QPushButton("등록")
        self.ok.setDefault(True)
        self.ok.setEnabled(bool(items))
        self.ok.clicked.connect(self._submit)
        foot.addWidget(cancel)
        foot.addWidget(self.ok)
        lay.addLayout(foot)

    def _bulk_target(self, key: str):
        for r in self.rows:
            r.set_target(key)

    def _bulk_check(self, on: bool):
        for r in self.rows:
            r.check.setChecked(on)

    def decisions(self) -> list[Decision]:
        return [d for r in self.rows if (d := r.decision()) is not None]

    def _submit(self):
        ds = self.decisions()
        self.submitted.emit(ds)
        self.accept()
