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

# 고양이 말풍선과 같은 톤: 크림 배경 + 살구 테두리 + 파스텔 버튼 (회색 업무용 느낌 제거)
REVIEW_QSS = """
QDialog#reviewDialog, QDialog#editDialog { background: #fffaf0; }
QLabel { color: #3a2e1e; }
QPushButton { background: #ffffff; border: 1.2px solid #f0c27b; border-radius: 9px; padding: 3px 10px; color: #3a2e1e; font-size: 12px; }
QPushButton:hover { background: #fff3e0; }
QPushButton:pressed { background: #ffe6c4; }
QPushButton:disabled { color: #b8ab9a; border-color: #eadfcf; background: #fdf8f1; }
QPushButton#btnOk { background: #f2a65a; border-color: #e0903f; color: white; font-weight: 600; }
QPushButton#btnOk:hover { background: #ea9a48; }
QPushButton#btnAux { border: none; background: transparent; color: #a08f7a; padding: 1px 6px; font-size: 11px; }
QPushButton#btnAux:hover { color: #f2a65a; background: transparent; }
/* 등록 대상 체크박스 — 작은 칩 느낌 */
QCheckBox#pickCal, QCheckBox#pickTask { font-size: 12px; color: #6b5d4c; spacing: 5px; padding: 1px 2px; }
QCheckBox#pickCal:checked { color: #d97706; font-weight: 600; }
QCheckBox#pickTask:checked { color: #2f855a; font-weight: 600; }
QCheckBox#pickCal:disabled, QCheckBox#pickTask:disabled { color: #cbbfae; }
#reviewCard { background: #ffffff; border: 1.5px solid #f0c27b; border-radius: 13px; }
QLineEdit, QComboBox, QDateEdit, QTimeEdit, QSpinBox { background: #ffffff; border: 1px solid #eadfcf; border-radius: 8px; padding: 2px 6px; }
"""


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
            "#targetBox { background: #fff6e8; border: 1px solid #f0c27b; border-radius: 10px; }")
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
        self.setStyleSheet("_Row { background: #ffffff; border: 2px solid #f0c27b; border-radius: 14px; }"
                           if on else "_Row { background: #fdf8f1; border: 2px dashed #eadfcf; border-radius: 14px; }")
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


class EditDialog(QDialog):
    """카드의 '수정…' — 항목 하나를 상세 편집 (_Row 전체: 대상·목록·제목·날짜·시간·종료·장소·알람·날짜 없음)."""

    def __init__(self, row: _Row, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("editDialog")
        self.setStyleSheet(REVIEW_QSS)
        self.setWindowTitle("상세 수정")
        self.setMinimumWidth(760)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self._row = row
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 10)
        lay.addWidget(row)
        row.show()
        foot = QHBoxLayout()
        foot.addStretch(1)
        cancel = QPushButton("닫기")
        cancel.clicked.connect(self.accept)
        foot.addWidget(cancel)
        lay.addLayout(foot)

    def done(self, r: int) -> None:
        # _Row 는 ReviewDialog 가 계속 쓰므로 이 창과 함께 파괴되지 않게 떼어낸다
        self.layout().removeWidget(self._row)
        self._row.setParent(None)
        self._row.hide()
        super().done(r)


class ReviewDialog(QDialog):
    """카드 한 장씩 넘기며 처리하는 검토 창.

    각 항목은 _Row(상세 편집기)를 모델로 갖고, 카드는 제목·일시·장소만 보여준다.
    📅 / ✅ / 📅+✅ / 건너뛰기 를 누르면 다음 카드로, 마지막엔 요약 카드 → 등록.
    알람은 설정의 기본값(_Row 초기값)을 그대로 쓰고, 바꾸려면 '수정…'.
    """
    submitted = Signal(list)   # list[Decision]

    def __init__(self, items: list[ScheduleItem], settings: cfg.ScheduleSettings, *,
                 source_label: str = "", warnings: list[str] | None = None,
                 preview_text: str = "", tasklists: list[tuple[str, str]] | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("reviewDialog")
        self.setStyleSheet(REVIEW_QSS)
        self.setWindowTitle(f"catmoa — {source_label}" if source_label else "catmoa")
        self.setMinimumWidth(330)
        self.resize(350, 228)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        tasklists = tasklists or []
        self._settings = settings
        self._warnings = list(warnings or [])
        self._preview_text = preview_text
        self._idx = 0

        # 모델: 항목별 상세 편집기 (숨김 상태로 보관, '수정…' 때만 EditDialog 에 붙임)
        self.rows: list[_Row] = []
        for it in items:
            row = _Row(it, settings, tasklists)
            row.hide()
            self.rows.append(row)
        self._done: list[bool] = [False] * len(self.rows)   # 카드에서 처리(선택/건너뜀)했는지

        lay = QVBoxLayout(self)
        lay.setContentsMargins(11, 8, 11, 8)
        lay.setSpacing(6)

        # 진행 표시
        top = QHBoxLayout()
        self.progress_label = QLabel()
        self.progress_label.setStyleSheet("color: #f2a65a; font-size: 11px; letter-spacing: 2px;")
        self.source_label = QLabel(source_label)
        self.source_label.setStyleSheet("color: #a08f7a; font-size: 10px;")
        top.addWidget(self.source_label)
        top.addStretch(1)
        top.addWidget(self.progress_label)
        lay.addLayout(top)

        # 카드
        self.card = QFrame(objectName="reviewCard")
        card_lay = QVBoxLayout(self.card)
        card_lay.setContentsMargins(12, 9, 12, 8)
        card_lay.setSpacing(3)
        self.card_title = QLabel()
        self.card_title.setWordWrap(True)
        self.card_title.setStyleSheet("font-size: 14px; font-weight: 600;")
        self.card_when = QLabel()
        self.card_when.setStyleSheet("font-size: 12px;")
        self.card_where = QLabel()
        self.card_where.setStyleSheet("font-size: 11px; color: #8a7a66;")
        self.card_where.setWordWrap(True)
        self.card_choice = QLabel()
        self.card_choice.setStyleSheet("font-size: 10px; color: #bcae9c;")
        card_lay.addWidget(self.card_title)
        card_lay.addWidget(self.card_when)
        card_lay.addWidget(self.card_where)
        card_lay.addStretch(1)
        card_lay.addWidget(self.card_choice)
        lay.addWidget(self.card, 1)

        # 등록 대상: 체크박스 두 개 (둘 다 끄면 건너뜀) + 다음/등록
        act = QHBoxLayout()
        act.setSpacing(10)
        self.chk_cal = QCheckBox("📅 캘린더", objectName="pickCal")
        self.chk_task = QCheckBox("✅ 태스크", objectName="pickTask")
        for c in (self.chk_cal, self.chk_task):
            c.toggled.connect(self._picked)
            act.addWidget(c)
        act.addStretch(1)
        self.btn_skip = QPushButton("건너뛰기")
        self.btn_skip.setObjectName("btnAux")
        self.btn_skip.clicked.connect(self._skip)
        self.btn_next = QPushButton("다음 →")
        self.btn_next.setObjectName("btnOk")
        self.btn_next.setMinimumWidth(72)
        self.btn_next.clicked.connect(self._next)
        self.ok = QPushButton("등록")
        self.ok.setObjectName("btnOk")
        self.ok.setMinimumWidth(78)
        self.ok.clicked.connect(self._submit)
        act.addWidget(self.btn_skip)
        act.addWidget(self.btn_next)
        act.addWidget(self.ok)
        lay.addLayout(act)

        # 보조 (작은 링크형)
        aux = QHBoxLayout()
        aux.setSpacing(4)
        self.btn_prev = QPushButton("← 이전")
        self.btn_prev.clicked.connect(self._prev)
        self.btn_edit = QPushButton("수정…")
        self.btn_edit.clicked.connect(self._edit)
        self.btn_rest = QPushButton("나머지 기본대로")
        self.btn_rest.setToolTip("남은 항목을 AI 제안(또는 설정의 기본 대상)대로 한 번에 처리")
        self.btn_rest.clicked.connect(self._rest_default)
        self.btn_cancel = QPushButton("취소")
        self.btn_cancel.clicked.connect(self.reject)
        for b in (self.btn_prev, self.btn_edit, self.btn_rest, self.btn_cancel):
            b.setObjectName("btnAux")
        aux.addWidget(self.btn_prev)
        aux.addStretch(1)
        aux.addWidget(self.btn_edit)
        aux.addWidget(self.btn_rest)
        aux.addWidget(self.btn_cancel)
        lay.addLayout(aux)

        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.setStyleSheet("color: #c58a2a; font-size: 10px;")
        lay.addWidget(self.note)

        # 단축키: 1/2 체크 토글, 3 둘 다, Enter 다음, S 건너뛰기, E 수정, ← 이전
        from PySide6.QtGui import QShortcut, QKeySequence
        for key, fn in (("1", self.chk_cal.toggle), ("2", self.chk_task.toggle),
                        ("3", lambda: self._choose({"calendar", "task"})), ("S", self._skip), ("E", self._edit),
                        ("Right", self._next), ("Left", self._prev), ("Backspace", self._prev)):
            QShortcut(QKeySequence(key), self, activated=fn)

        self._render()

    # ------------------------------------------------------------ 표시
    @property
    def at_summary(self) -> bool:
        return self._idx >= len(self.rows)

    def _render(self) -> None:
        n = len(self.rows)
        for w in (self.chk_cal, self.chk_task, self.btn_skip, self.btn_next, self.btn_edit, self.btn_rest):
            w.setVisible(not self.at_summary and n > 0)
        self.btn_prev.setVisible(n > 0 and self._idx > 0)
        self.ok.setVisible(self.at_summary or n == 0)
        self.btn_cancel.setVisible(True)
        self.note.setText("  ·  ".join(self._warnings) if self._warnings else "")
        self.note.setVisible(bool(self._warnings))

        if n == 0:
            self.progress_label.setText("")
            self.card_title.setText("일정을 찾지 못했어요")
            self.card_when.setText("")
            self.card_where.setText("")
            self.card_choice.setText("")
            self.ok.setEnabled(False)
            return

        if self.at_summary:
            ds = self.decisions()
            cal = sum(1 for d in ds if "calendar" in d.targets)
            task = sum(1 for d in ds if "task" in d.targets)
            skipped = n - len(ds)
            self.progress_label.setText("●" * min(n, 12) + f"  {n} / {n}")
            self.card_title.setText(f"{len(ds)}개 등록 준비 완료" if ds else "등록할 항목이 없어요")
            parts = []
            if cal:
                parts.append(f"📅 캘린더 {cal}")
            if task:
                parts.append(f"✅ 태스크 {task}")
            if skipped:
                parts.append(f"건너뜀 {skipped}")
            self.card_when.setText("  ·  ".join(parts))
            self.card_where.setText("\n".join(f"• {d.item.title} — {d.item.describe_when()}" for d in ds[:8])
                                    + ("\n…" if len(ds) > 8 else ""))
            self.card_choice.setText("← 이전 으로 돌아가 바꿀 수 있어요")
            self.ok.setEnabled(bool(ds))
            self.ok.setDefault(True)
            return

        row = self.rows[self._idx]
        it = row.item
        dots = ("●" * self._idx + "◉" + "○" * (n - self._idx - 1)) if n <= 12 else ""
        self.progress_label.setText(f"{dots}  {self._idx + 1} / {n}".strip())
        self.card_title.setText(it.title)
        when = "날짜 없음 (마감 없는 할 일)" if row.no_date.isChecked() else self._describe_row(row)
        self.card_when.setText(("🗓  " if not row.no_date.isChecked() else "☑  ") + when)
        where = []
        if row.location.text().strip():
            where.append("📍 " + row.location.text().strip())
        if row.task.isChecked() and row.tasklist.currentData():
            where.append("📂 " + row.tasklist.currentText())
        self.card_where.setText("   ".join(where))
        # 현재 선택 상태를 체크박스에 반영 (돌아왔을 때 / AI 제안 그대로)
        t = row.targets()
        undated = row.no_date.isChecked()
        for c, key in ((self.chk_cal, "calendar"), (self.chk_task, "task")):
            c.blockSignals(True)
            c.setChecked(key in t)
            c.blockSignals(False)
        self.chk_cal.setEnabled(not undated)
        self.chk_cal.setToolTip("날짜 없는 할 일은 캘린더에 넣을 수 없어요" if undated else "")
        label = {frozenset({"calendar"}): "📅 캘린더", frozenset({"task"}): "✅ 태스크",
                 frozenset({"calendar", "task"}): "📅+✅ 둘 다"}.get(frozenset(t), "건너뜀")
        self.card_choice.setText(f"{'선택됨' if self._done[self._idx] else 'AI 제안'} · {label}")
        self.btn_next.setDefault(True)

    @staticmethod
    def _describe_row(row: _Row) -> str:
        d = row.date.date()
        s = f"{d.toString('yyyy-MM-dd')} ({'월화수목금토일'[d.dayOfWeek() - 1]})"
        if row.all_day.isChecked():
            if row.has_end.isChecked() and row.end_date.date() != d:
                s += f" ~ {row.end_date.date().toString('yyyy-MM-dd')}"
            return s + "  종일"
        s += " " + row.time.time().toString("HH:mm")
        if row.has_end.isChecked():
            s += "~" + row.end_time.time().toString("HH:mm")
        return s

    # ------------------------------------------------------------ 동작
    def _picked(self, *_) -> None:
        """체크박스를 건드리면 현재 카드에 바로 반영 (넘기지는 않는다)."""
        if self.at_summary or not self.rows:
            return
        row = self.rows[self._idx]
        targets = set()
        if self.chk_cal.isChecked() and not row.no_date.isChecked():
            targets.add("calendar")
        if self.chk_task.isChecked():
            targets.add("task")
        row.set_targets(targets)
        self._done[self._idx] = True
        self._render()

    def _next(self) -> None:
        """현재 체크 상태대로 확정하고 다음 카드로 (둘 다 꺼져 있으면 건너뜀)."""
        if self.at_summary or not self.rows:
            return
        self._done[self._idx] = True
        self._idx += 1
        self._render()

    def _choose(self, targets: set[str]) -> None:
        """대상을 지정하고 바로 다음 카드로 (단축키 3 / 하위 호환)."""
        if self.at_summary or not self.rows:
            return
        row = self.rows[self._idx]
        if row.no_date.isChecked():
            targets = targets & {"task"} or {"task"}
        row.set_targets(set(targets))
        self._done[self._idx] = True
        self._idx += 1
        self._render()

    def _skip(self) -> None:
        if self.at_summary or not self.rows:
            return
        self.rows[self._idx].set_targets(set())
        self._done[self._idx] = True
        self._idx += 1
        self._render()

    def _prev(self) -> None:
        if self._idx > 0:
            self._idx -= 1
            self._render()

    def _edit(self) -> None:
        if self.at_summary or not self.rows:
            return
        dlg = EditDialog(self.rows[self._idx], self)
        dlg.exec()
        self._render()

    def _rest_default(self) -> None:
        """남은 카드를 현재 제안(_Row 초기 대상)대로 처리하고 요약으로."""
        for i in range(self._idx, len(self.rows)):
            self._done[i] = True
        self._idx = len(self.rows)
        self._render()

    # ------------------------------------------------------------ 하위 호환 / 일괄
    def _bulk_target(self, key: str):
        self._bulk_targets({key})

    def _bulk_targets(self, targets: set[str]):
        for r in self.rows:
            r.set_targets(targets)
        self._render()

    def _bulk_check(self, on: bool):
        """on=False: 모두 끄기(등록 안 함), on=True: 기본 대상으로 되돌리기."""
        for r in self.rows:
            r.set_targets(default_targets(r.item, self._settings) if on else set())
        self._render()

    def decisions(self) -> list[Decision]:
        return [d for r in self.rows if (d := r.decision()) is not None]

    def _submit(self):
        ds = self.decisions()
        self.submitted.emit(ds)
        self.accept()
