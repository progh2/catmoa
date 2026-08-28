"""쿨메신저 받은 쪽지 읽기 전용 리더.

저장소: %LOCALAPPDATA%\\CoolMessenger\\Memo\\*.udb — 암호화 없는 SQLite(WAL).
접근 규칙 (dacisosl/coolm-helper, MIT 참고): 원본은 절대 쓰기 모드로 열지 않는다.
udb + -wal + -shm 을 임시 폴더에 복사한 뒤 복사본을 mode=ro 로 연다. 사용 후 복사본 삭제.
"""
from __future__ import annotations

import glob
import os
import re
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

REQUIRED_COLS = {"MessageKey", "Sender", "ReceiveDate", "Title", "MessageText"}


class CoolmError(Exception):
    """사용자에게 보여줄 오류 (폴더 없음, 스키마 불일치 등)."""


@dataclass
class Message:
    key: int
    sender: str
    received: datetime
    title: str
    body: str
    is_unread: bool = False

    @property
    def text(self) -> str:
        return self.to_text()

    def to_text(self, history_chars: int = 1200) -> str:
        """LLM 입력용 텍스트. 답장에 쌓인 이전 대화는 분리해 '참고용'으로 뒤에 붙인다 (history_chars=0 이면 제외)."""
        parts = []
        if self.title.strip():
            parts.append(f"제목: {self.title.strip()}")
        if self.sender.strip():
            parts.append(f"보낸 사람: {self.sender.strip()}")
        parts.append(f"받은 시각: {self.received:%Y-%m-%d %H:%M}")
        recent, older = split_recent(self.body)
        if older:
            parts.append("")
            parts.append("[최근 내용]")
            parts.append(recent or "(본문 없음 — 아래 이전 대화만 있음)")
            if history_chars > 0:
                parts.append("")
                parts.append("[이전 대화 (참고용 — 최근 내용이 가리키는 것을 해석할 때만 참고, 지나간 일정은 추출하지 말 것)]")
                parts.append(older[:history_chars] + ("\n…(이하 생략)" if len(older) > history_chars else ""))
        else:
            parts.append("")
            parts.append(recent)
        return "\n".join(parts)


# ---------------------------------------------------------------- 인용된 이전 대화 분리

_QUOTE_LINE_RE = re.compile(
    r"^\s*("
    r"-{3,}\s*(original\s*message|원본\s*메시지|원본|이전\s*(메시지|쪽지|대화))\s*-{3,}"   # ----- 원본 메시지 -----
    r"|[-=_─━]{6,}"                                                                    # 긴 구분선
    r"|on\s.+\swrote:"                                                                 # On ... wrote:
    r"|\d{4}[./-]\s?\d{1,2}[./-]\s?\d{1,2}.*(님이\s*(작성|씀)|wrote|작성함?)\s*[:：]?"     # 2026-06-08 홍길동님이 작성:
    r"|(re|회신|답장|fw|fwd|전달)\s*[:：]\s*$"
    r")\s*$",
    re.I,
)
# 쿨메신저 실제 인용/전달 표기: "홍길동님이 보낸글 >>", "보낸 메시지 전달 >>", "메시지 전달 >>" (앞에 이름 등 최대 100자)
_COOLM_MARK_RE = re.compile(r"^[^\n]{0,100}?(?:님이\s*보낸\s*글|보낸\s*메시지(?:\s*전달)?|메시지\s*전달)\s*>>")
_HEADER_KEY_RE = re.compile(r"^\s*(from|보낸\s*사람|발신|발신자|sent|보낸\s*날짜|날짜|date|to|받는\s*사람|수신|subject|제목)\s*[:：]", re.I)
_GT_RE = re.compile(r"^\s*>")


def split_recent(body: str) -> tuple[str, str]:
    """(최근 내용, 인용된 이전 대화). 이전 대화가 없으면 두 번째는 ''."""
    lines = (body or "").replace("\r", "").split("\n")
    cut = None
    for i, line in enumerate(lines):
        if i == 0 and not line.strip():
            continue
        if _COOLM_MARK_RE.match(line):          # 쿨메신저 표기는 첫 줄이어도 인용 시작 (본문이 비어 있는 전달)
            cut = i
            break
        if _QUOTE_LINE_RE.match(line):
            cut = i
            break
        # 헤더 블록: '보낸 사람:' 류가 2줄 이상 연달아 오면 인용 시작
        if _HEADER_KEY_RE.match(line):
            window = [l for l in lines[i:i + 4] if l.strip()]
            if sum(1 for l in window if _HEADER_KEY_RE.match(l)) >= 2 and i > 0:
                cut = i
                break
        # '>' 인용: 이 줄부터 끝까지 비어있지 않은 줄의 대부분이 '>' 로 시작
        if _GT_RE.match(line) and i > 0:
            rest = [l for l in lines[i:] if l.strip()]
            if rest and sum(1 for l in rest if _GT_RE.match(l)) >= max(2, int(len(rest) * 0.6)):
                cut = i
                break
    if cut is None:
        return (body or "").strip(), ""
    recent = "\n".join(lines[:cut]).strip()
    older = "\n".join(lines[cut:]).strip()
    # 인용 기호 제거해 읽기 쉽게
    older = "\n".join(re.sub(r"^\s*(>\s?)+", "", l) for l in older.split("\n")).strip()
    return recent, older


def default_memo_dir() -> str:
    base = os.environ.get("LOCALAPPDATA", "")
    return str(Path(base) / "CoolMessenger" / "Memo") if base else ""


def parse_receive_date(s: str) -> datetime:
    """'2026/07/16 17:04:52 (목)' → datetime."""
    return datetime.strptime(str(s)[:19], "%Y/%m/%d %H:%M:%S")


def find_active_udb(memo_dir: str) -> str:
    """폴더 내 가장 최근 수정된 .udb (구버전 파일 공존 대비)."""
    if not memo_dir or not os.path.isdir(memo_dir):
        raise CoolmError(f"쿨메신저 메시지 폴더가 없습니다: {memo_dir or '(미설정)'}")
    cands = glob.glob(os.path.join(memo_dir, "*.udb"))
    if not cands:
        raise CoolmError(f"메시지 DB(.udb)를 찾을 수 없습니다: {memo_dir}")
    return max(cands, key=os.path.getmtime)


def _copy_shared(src: str, dst: str) -> None:
    with open(src, "rb") as fin, open(dst, "wb") as fout:
        shutil.copyfileobj(fin, fout, 1024 * 1024)


class CoolmReader:
    """with 문으로 사용. 복사본을 읽기 전용으로 연다."""

    def __init__(self, memo_dir: str):
        self.memo_dir = memo_dir
        self._tmp: str | None = None
        self._con: sqlite3.Connection | None = None

    def __enter__(self) -> "CoolmReader":
        src = find_active_udb(self.memo_dir)
        self._tmp = tempfile.mkdtemp(prefix="catmoa_coolm_")
        dst = os.path.join(self._tmp, "copy.udb")
        try:
            for ext in ("", "-wal", "-shm"):
                if os.path.exists(src + ext):
                    _copy_shared(src + ext, dst + ext)
            self._con = sqlite3.connect(f"file:{dst}?mode=ro", uri=True)
            self._validate()
        except (OSError, sqlite3.Error) as e:
            self.__exit__(None, None, None)
            raise CoolmError(f"쿨메신저 DB를 열 수 없습니다: {e}") from e
        except CoolmError:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *exc) -> None:
        if self._con is not None:
            self._con.close()
            self._con = None
        if self._tmp:
            shutil.rmtree(self._tmp, ignore_errors=True)
            self._tmp = None

    def _validate(self) -> None:
        cur = self._con.cursor()
        tables = {r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "tbl_recv" not in tables:
            raise CoolmError("쿨메신저 DB 구조가 예상과 다릅니다 (tbl_recv 없음). 쿨메신저 버전이 바뀌었을 수 있습니다.")
        cols = {r[1] for r in cur.execute("PRAGMA table_info(tbl_recv)")}
        missing = REQUIRED_COLS - cols
        if missing:
            raise CoolmError(f"쿨메신저 DB에 필수 컬럼이 없습니다: {sorted(missing)}")
        self._has_deleted = "DeletedDate" in cols
        self._has_unread = "IsUnRead" in cols

    def latest_key(self) -> int:
        row = self._con.execute("SELECT MAX(MessageKey) FROM tbl_recv").fetchone()
        return int(row[0] or 0)

    def messages_after(self, key: int, limit: int = 50) -> list[Message]:
        """MessageKey > key 인 쪽지 (오래된 순). 삭제된 쪽지는 제외."""
        where = "MessageKey > ?"
        if self._has_deleted:
            where += " AND DeletedDate IS NULL"
        unread_col = "IsUnRead" if self._has_unread else "0"
        rows = self._con.execute(
            f"SELECT MessageKey, Sender, ReceiveDate, Title, MessageText, {unread_col} FROM tbl_recv "
            f"WHERE {where} ORDER BY MessageKey ASC LIMIT ?", (int(key), int(limit))).fetchall()
        return [m for m in (_row(r) for r in rows) if m is not None]

    def latest_messages(self, limit: int = 10) -> list[Message]:
        where = "DeletedDate IS NULL" if self._has_deleted else "1=1"
        unread_col = "IsUnRead" if self._has_unread else "0"
        rows = self._con.execute(
            f"SELECT MessageKey, Sender, ReceiveDate, Title, MessageText, {unread_col} FROM tbl_recv "
            f"WHERE {where} ORDER BY MessageKey DESC LIMIT ?", (int(limit),)).fetchall()
        return [m for m in (_row(r) for r in rows) if m is not None]


def _row(r) -> Message | None:
    key, sender, rdate, title, body, unread = r
    try:
        received = parse_receive_date(rdate)
    except (ValueError, TypeError):
        return None
    return Message(key=int(key), sender=sender or "", received=received, title=title or "",
                   body=body or "", is_unread=bool(unread))


# ---------------------------------------------------------------- 테스트/데모용 가짜 udb

def create_fake_udb(memo_dir: str | Path, messages: list[dict] | None = None, name: str = "coolm.udb") -> str:
    """쿨메신저와 같은 구조의 udb 를 만든다 (macOS/Linux 개발·데모용).

    messages: [{"sender", "title", "body", "received": datetime, "unread": bool}]
    """
    memo_dir = Path(memo_dir)
    memo_dir.mkdir(parents=True, exist_ok=True)
    path = memo_dir / name
    con = sqlite3.connect(path)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("""CREATE TABLE IF NOT EXISTS tbl_recv (
        MessageKey INTEGER PRIMARY KEY AUTOINCREMENT,
        Sender TEXT, ReceiveDate TEXT, Title TEXT, MessageText TEXT, MessageBody BLOB,
        IsUnRead INTEGER DEFAULT 1, DeletedDate TEXT)""")
    con.execute("CREATE TABLE IF NOT EXISTS tbl_member (MemberID TEXT, MemberName TEXT)")
    for m in messages or []:
        append_fake_message(con, m)
    con.commit()
    con.close()
    return str(path)


def append_fake_message(con_or_path, m: dict) -> int:
    own = isinstance(con_or_path, (str, Path))
    con = sqlite3.connect(con_or_path) if own else con_or_path
    received: datetime = m.get("received") or datetime.now()
    wd = "월화수목금토일"[received.weekday()]
    cur = con.execute(
        "INSERT INTO tbl_recv (Sender, ReceiveDate, Title, MessageText, IsUnRead) VALUES (?,?,?,?,?)",
        (m.get("sender", "홍길동"), f"{received:%Y/%m/%d %H:%M:%S} ({wd})", m.get("title", ""),
         m.get("body", ""), 1 if m.get("unread", True) else 0))
    key = cur.lastrowid
    if own:
        con.commit()
        con.close()
    return int(key)
