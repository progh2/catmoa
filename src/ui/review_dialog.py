"""일정 검토 다이얼로그.

추출된 항목을 행 단위로 보여주고, 항목별로 📅캘린더 / ✅태스크 체크(둘 다 가능), 태스크 목록(카테고리),
알람, 내용을 편집한 뒤 [등록]을 누르면 Decision 목록을 돌려준다.
둘 다 선택하면 캘린더에는 마감(또는 일정)으로, 태스크에는 할 일로 들어간다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from PySide6.QtCore import QDate, Qt, QTime, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QScrollArea, QSpinBox, QTimeEdit, QVBoxLayout, QWidget,
)

from src import config as cfg
from src.extract.schema import ScheduleItem

DEFAULT_LIST_LABEL = "(기본 목록)"


@dataclass
class Decision:
    item: ScheduleItem
    targets: set[str] = field(default_factory=set)   # {"calendar", "task"}
    alarm_minutes: int | None = None                  # None = 알람 없음
    tasklist_id: str = ""                             # "" = 설정의 기본 목록
    tasklist_name: str = ""
    # 중복 검사 결과 처리: target → (action, 기존 항목 dict, tasklist_id). action: "skip" | "update" | "create"
    dedupe: dict = field(default_factory=dict)

    @property
    def target(self) -> str:
        """대표 대상 (로그/요약용)."""
        if self.targets == {"calendar", "task"}:
            return "both"
        return "calendar" if "calendar" in self.targets else "task"


def default_targets(item: ScheduleItem, settings: cfg.ScheduleSettings) -> set[str]:
    mode = settings.default_target
    if mode == "calendar":
        return {"calendar"}
    if mode == "task":
        return {"task"}
    if item.undated:
        return {"task"}
    if mode == "both":
        return {"calendar", "task"}
    return {"calendar"} if item.kind == "event" else {"task"}


def _norm(s: str) -> str:
    return "".join(s.split()).lower()


class _Row(QFrame):
    def __init__(self, item: ScheduleItem, settings: cfg.ScheduleSettings,
                 tasklists: list[tuple[str, str]], parent=None):
        super().__init__(parent)
        self.item = item
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("_Row { background: palette(base); border: 1px solid palette(mid); border-radius: 8px; }")

        # ---- 1행: [등록 대상: 📅 · ✅ · 태스크 목록] · 제목 · 알람   (📅/✅ 둘 다 끄면 등록하지 않음)
        targets = default_targets(item, settings)
        self.cal = QCheckBox("📅 캘린더")
        self.cal.setToolTip("캘린더에 등록 (태스크와 함께 선택하면 마감일 일정으로)")
        self.cal.setChecked("calendar" in targets)
        self.task = QCheckBox("✅ 태스크")
        self.task.setToolTip("Google Tasks에 할 일로 등록")
        self.task.setChecked("task" in targets)
        self.tasklist = QComboBox()
        self.tasklist.setToolTip("넣을 태스크 목록 (카테고리)")
        self.tasklist.addItem(DEFAULT_LIST_LABEL, "")
        for tid, name in tasklists:
            self.tasklist.addItem(name, tid)
        self._preselect_tasklist(item, settings, tasklists)
        self.title = QLineEdit(item.title)
        self.title.setPlaceholderText("제목")
        self.alarm = QCheckBox("알람")
        self.alarm.setChecked(settings.alarm_enabled)
        self.alarm_min = QSpinBox()
        self.alarm_min.setRange(0, 7 * 24 * 60)
        self.alarm_min.setSuffix("분 전")
        self.alarm_min.setValue(item.alarm_minutes if item.alarm_minutes is not None else settings.alarm_minutes)

        # 대상 선택 묶음 — 제목·알람과 시각적으로 구분
        self.target_box = QFrame(objectName="targetBox")
        self.target_box.setStyleSheet(
            "#targetBox { background: palette(alternate-base); border: 1px solid palette(mid); border-radius: 6px; }")
        tb = QHBoxLayout(self.target_box)
        tb.setContentsMargins(8, 2, 8, 2)
        tb.setSpacing(8)
        tb.addWidget(self.cal)
        tb.addWidget(self.task)
        tb.addWidget(self.tasklist)

        r1 = QHBoxLayout()
        r1.setSpacing(10)
        r1.addWidget(self.target_box)
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
        self.end_time = QTimeEdit(QTime(end.hour, end.minute) if end and not item.all_day
                                  else QTime(min(item.start.hour + 1, 23), item.start.minute))
        self.end_time.setDisplayFormat("HH:mm")
        self.has_end = QCheckBox("종료")
        self.has_end.setChecked(bool(end))
        self.end_date = QDateEdit(QDate(end.year, end.month, end.day) if end else self.date.date())
        self.end_date.setCalendarPopup(True)
        self.end_date.setDisplayFormat("yyyy-MM-dd")
        self.location = QLineEdit(item.location or "")
        self.location.setPlaceholderText("장소")
        self.no_date = QCheckBox("날짜 없음")
        self.no_date.setToolTip("마감 없는 할 일 — 태스크에만 넣을 수 있습니다")
        self.no_date.setChecked(item.undated)
        if item.undated:
            self.cal.setChecked(False)

        r2 = QHBoxLayout()
        r2.addSpacing(8)
        r2.addWidget(self.no_date)
        r2.addWidget(self.date)
        r2.addWidget(self.all_day)
        r2.addWidget(self.time)
        r2.addWidget(self.has_end)
        r2.addWidget(self.end_date)
        r2.addWidget(self.end_time)
        r2.addWidget(self.location, 1)

        # ---- 3행: 근거/메모
        self.notes = QLabel()
        self.notes.setStyleSheet("color: palette(mid); font-size: 11px;")
        self.notes.setWordWrap(True)
        meta = []
        if item.source:
            meta.append(item.source)
        meta.append(f"확신 {int(item.confidence * 100)}%")
        if item.category:
            meta.append(f"제안 목록: {item.category}")
        if item.notes:
            meta.append(item.notes)
        self.notes.setText(" · ".join(meta))

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(4)
        lay.addLayout(r1)
        lay.addLayout(r2)
        lay.addWidget(self.notes)

        for w in (self.all_day, self.has_end, self.cal, self.task, self.alarm, self.no_date):
            w.toggled.connect(self._sync_enabled)
        self._sync_enabled()

    @property
    def selected(self) -> bool:
        """📅 또는 ✅ 가 켜져 있으면 등록 대상."""
        return bool(self.targets())

    def _preselect_tasklist(self, item, settings, tasklists):
        want = None
        if item.category:
            key = _norm(item.category)
            want = next((tid for tid, name in tasklists if _norm(name) == key), None)
        if want is None and settings.tasklist_id:
            want = settings.tasklist_id
        idx = self.tasklist.findData(want) if want else -1
        self.tasklist.setCurrentIndex(idx if idx >= 0 else 0)

    def _sync_enabled(self, *_):
        on = self.selected
        for w in (self.title, self.alarm, self.date, self.all_day, self.time,
                  self.has_end, self.end_date, self.end_time, self.location):
            w.setEnabled(on)
        self.tasklist.setEnabled(self.task.isChecked())
        self.setStyleSheet("_Row { background: palette(base); border: 1px solid palette(mid); border-radius: 8px; }"
                           if on else "_Row { background: palette(window); border: 1px dashed palette(mid); border-radius: 8px; }")
        undated = self.no_date.isChecked()
        if undated:
            # 날짜 없는 할 일: 캘린더 불가, 날짜/시간/알람 비활성
            if self.cal.isChecked():
                self.cal.setChecked(False)
            self.cal.setEnabled(False)
            for w in (self.date, self.all_day, self.time, self.has_end, self.end_date, self.end_time, self.alarm, self.alarm_min):
                w.setEnabled(False)
            return
        self.cal.setEnabled(True)
        if on:
            self.alarm_min.setEnabled(self.alarm.isChecked())
            all_day = self.all_day.isChecked()
            self.time.setEnabled(not all_day)
            self.end_time.setEnabled(self.has_end.isChecked() and not all_day)
            self.end_date.setEnabled(self.has_end.isChecked())
        else:
            self.alarm_min.setEnabled(False)

    def set_targets(self, targets: set[str]):
        self.cal.setChecked("calendar" in targets)
        self.task.setChecked("task" in targets)

    def targets(self) -> set[str]:
        t = set()
        if self.cal.isChecked():
            t.add("calendar")
        if self.task.isChecked():
            t.add("task")
        return t

    def decision(self) -> Decision | None:
        if not self.selected:
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
        targets = self.targets()
        undated = self.no_date.isChecked()
        if undated:
            targets.discard("calendar")
            if not targets:
                return None
        alarm = None if undated else (self.alarm_min.value() if self.alarm.isChecked() else None)
        item = self.item.model_copy(update={
            "title": self.title.text().strip() or self.item.title,
            "start": start, "end": end, "all_day": all_day, "undated": undated,
            "kind": "task" if targets == {"task"} else ("event" if targets == {"calendar"} else self.item.kind),
            "category": self.tasklist.currentText() if self.tasklist.currentData() else self.item.category,
            "location": self.location.text().strip() or None,
            "alarm_minutes": alarm,
        })
        return Decision(item=item, targets=targets, alarm_minutes=alarm,
                        tasklist_id=self.tasklist.currentData() or "",
                        tasklist_name=self.tasklist.currentText() if self.tasklist.currentData() else "")


class ReviewDialog(QDialog):
    submitted = Signal(list)   # list[Decision]

    def __init__(self, items: list[ScheduleItem], settings: cfg.ScheduleSettings, *,
                 source_label: str = "", warnings: list[str] | None = None,
                 preview_text: str = "", tasklists: list[tuple[str, str]] | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(f"일정 검토 — {source_label}" if source_label else "일정 검토")
        self.setMinimumWidth(820)
        self.resize(880, min(160 + 130 * max(len(items), 1), 720))
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        tasklists = tasklists or []
        self._settings = settings

        head = QLabel(f"<b>{len(items)}개</b>의 일정을 찾았습니다. 항목마다 <b>등록 대상</b>(📅 캘린더 / ✅ 태스크)을 고르세요 — "
                      "둘 다 고르면 캘린더엔 마감일로, 태스크엔 할 일로 들어가고, <b>둘 다 끄면 등록하지 않습니다</b>." if items
                      else "일정을 찾지 못했습니다.")
        head.setWordWrap(True)
        lay = QVBoxLayout(self)
        lay.addWidget(head)
        for w in warnings or []:
            wl = QLabel(f"⚠ {w}")
            wl.setStyleSheet("color: #b8860b;")
            lay.addWidget(wl)

        bulk = QHBoxLayout()
        for label, fn in (("모두 📅 캘린더", lambda: self._bulk_targets({"calendar"})),
                          ("모두 ✅ 태스크", lambda: self._bulk_targets({"task"})),
                          ("모두 📅+✅", lambda: self._bulk_targets({"calendar", "task"})),
                          ("모두 끄기 (등록 안 함)", lambda: self._bulk_check(False))):
            b = QPushButton(label)
            b.clicked.connect(fn)
            bulk.addWidget(b)
        bulk.addStretch(1)
        lay.addLayout(bulk)

        self.rows: list[_Row] = []
        body = QWidget()
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(0, 0, 0, 0)
        for it in items:
            row = _Row(it, settings, tasklists)
            self.rows.append(row)
            body_lay.addWidget(row)
        body_lay.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        lay.addWidget(scroll, 1)

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

    # 하위 호환 (테스트/외부에서 단일 대상 일괄 지정)
    def _bulk_target(self, key: str):
        self._bulk_targets({key})

    def _bulk_targets(self, targets: set[str]):
        for r in self.rows:
            r.set_targets(targets)

    def _bulk_check(self, on: bool):
        """on=False: 모두 끄기(등록 안 함), on=True: 기본 대상으로 되돌리기."""
        for r in self.rows:
            r.set_targets(default_targets(r.item, self._settings) if on else set())

    def decisions(self) -> list[Decision]:
        return [d for r in self.rows if (d := r.decision()) is not None]

    def _submit(self):
        ds = self.decisions()
        self.submitted.emit(ds)
        self.accept()
