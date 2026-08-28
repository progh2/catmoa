"""중복 실행 방지.

규칙 (사용자 요청):
- 이미 catmoa 가 떠 있으면 두 번째 창을 만들지 않는다. 대신 떠 있던 고양이를 보여주고 조용히 종료.
- 떠 있던 게 **옛날 버전**이면 그쪽을 종료시키고 새 버전이 자리를 잇는다.

두 가지를 함께 쓴다.
1. 잠금 파일(`instance.json`, 설정 폴더): pid + version + 로컬 소켓 이름. 버전 비교와 강제 종료용.
2. QLocalServer: 살아 있는 인스턴스에 "show"(창 보이기) / "quit"(종료) 를 전달하는 통로.

잠금 파일만으로는 "창을 다시 보여줘"를 할 수 없고, 소켓만으로는 상대 버전을 알 수 없어 둘 다 필요하다.
(1.4.10 이전 버전은 잠금 파일도 서버도 없어서 감지되지 않는다 — 그 경우는 그냥 둘 다 뜬다.)
"""
from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from src import __version__, config as cfg
from src.updater import parse_version

log = logging.getLogger(__name__)

LOCK_NAME = "instance.json"
SERVER_NAME = "catmoa-single-instance"
MSG_SHOW = b"show\n"
MSG_QUIT = b"quit\n"


def lock_path() -> Path:
    return cfg.config_dir() / LOCK_NAME


@dataclass
class Existing:
    pid: int
    version: str
    server: str = SERVER_NAME


# ---------------------------------------------------------------- 프로세스 확인/종료

def pid_alive(pid: int) -> bool:
    """살아 있는 프로세스인지. Windows 의 os.kill 은 시그널 0 도 강제 종료라 쓰면 안 된다."""
    if pid <= 0 or pid == os.getpid():
        return pid == os.getpid()
    if sys.platform == "win32":  # pragma: no cover - Windows 전용
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION, STILL_ACTIVE = 0x1000, 259
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not h:
            return False
        try:
            code = ctypes.c_ulong()
            ok = k32.GetExitCodeProcess(h, ctypes.byref(code))
            return bool(ok) and code.value == STILL_ACTIVE
        finally:
            k32.CloseHandle(h)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:      # 다른 사용자 소유 = 살아 있음
        return True
    return True


def terminate(pid: int, timeout: float = 8.0) -> bool:
    """정상 종료 요청 → 안 죽으면 강제 종료. 죽었으면 True."""
    if not pid_alive(pid):
        return True
    try:
        if sys.platform == "win32":  # pragma: no cover - Windows 전용
            os.system(f"taskkill /PID {int(pid)} /T > NUL 2>&1")
        else:
            os.kill(pid, signal.SIGTERM)
    except OSError as e:
        log.warning("기존 인스턴스(%s) 종료 요청 실패: %s", pid, e)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not pid_alive(pid):
            return True
        time.sleep(0.2)
    try:
        if sys.platform == "win32":  # pragma: no cover - Windows 전용
            os.system(f"taskkill /F /PID {int(pid)} /T > NUL 2>&1")
        else:
            os.kill(pid, signal.SIGKILL)
    except OSError:
        pass
    for _ in range(15):
        if not pid_alive(pid):
            return True
        time.sleep(0.2)
    return not pid_alive(pid)


# ---------------------------------------------------------------- 잠금 파일

def read_lock() -> Existing | None:
    p = lock_path()
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return Existing(pid=int(d["pid"]), version=str(d.get("version", "0")),
                        server=str(d.get("server", SERVER_NAME)))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def write_lock(version: str = __version__) -> None:
    p = lock_path()
    try:
        p.write_text(json.dumps({"pid": os.getpid(), "version": version, "server": SERVER_NAME,
                                 "started": time.time()}, ensure_ascii=False), encoding="utf-8")
    except OSError as e:
        log.warning("실행 잠금 파일을 쓸 수 없습니다: %s", e)


def clear_lock() -> None:
    """내가 쓴 잠금만 지운다 (다른 인스턴스가 이어받았으면 건드리지 않는다)."""
    ex = read_lock()
    if ex is not None and ex.pid != os.getpid():
        return
    try:
        lock_path().unlink(missing_ok=True)
    except OSError:
        pass


# ---------------------------------------------------------------- 로컬 소켓

def _send(server: str, payload: bytes, wait_ms: int = 800) -> bool:
    from PySide6.QtNetwork import QLocalSocket

    s = QLocalSocket()
    s.connectToServer(server)
    if not s.waitForConnected(wait_ms):
        return False
    s.write(payload)
    s.flush()
    s.waitForBytesWritten(wait_ms)
    s.disconnectFromServer()
    return True


def ping_show(server: str = SERVER_NAME) -> bool:
    """살아 있는 인스턴스에 '창을 보여줘'를 전달."""
    return _send(server, MSG_SHOW)


def ping_quit(server: str = SERVER_NAME) -> bool:
    """살아 있는 인스턴스에 '스스로 종료해'를 전달 (강제 종료보다 안전하다)."""
    return _send(server, MSG_QUIT)


class InstanceServer:
    """살아 있는 인스턴스 쪽. `show_requested` / `quit_requested` 콜백을 받는다."""

    def __init__(self, on_show=None, on_quit=None, name: str = SERVER_NAME):
        from PySide6.QtNetwork import QLocalServer

        self._on_show, self._on_quit = on_show, on_quit
        self._conns: list = []
        self.server = QLocalServer()
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        QLocalServer.removeServer(name)      # 비정상 종료로 남은 소켓 정리
        self.ok = self.server.listen(name)
        if self.ok:
            self.server.newConnection.connect(self._accept)
        else:
            log.warning("단일 인스턴스 서버를 열지 못했습니다: %s", self.server.errorString())

    def _accept(self) -> None:
        conn = self.server.nextPendingConnection()
        if conn is None:
            return
        self._conns.append(conn)
        conn.readyRead.connect(lambda c=conn: self._read(c))
        conn.disconnected.connect(lambda c=conn: self._conns.remove(c) if c in self._conns else None)

    def _read(self, conn) -> None:
        data = bytes(conn.readAll().data())
        if MSG_QUIT.strip() in data:
            log.info("새 버전이 실행되어 종료합니다.")
            if self._on_quit:
                self._on_quit()
        elif MSG_SHOW.strip() in data:
            log.info("이미 실행 중 — 기존 창을 보여줍니다.")
            if self._on_show:
                self._on_show()

    def close(self) -> None:
        try:
            self.server.close()
        except RuntimeError:
            pass


# ---------------------------------------------------------------- 진입 판단

def take_over(version: str = __version__) -> str:
    """실행 전에 호출. 반환값:

    - "run"   : 그대로 실행 (잠금 확보 완료)
    - "exit"  : 이미 같은/최신 버전이 떠 있음 → 그 창을 띄웠으니 조용히 종료
    """
    ex = read_lock()
    if ex is None or ex.pid == os.getpid() or not pid_alive(ex.pid):
        write_lock(version)
        return "run"

    if parse_version(ex.version) >= parse_version(version):
        log.info("이미 실행 중입니다 (pid=%s, %s) — 기존 창을 보여주고 종료", ex.pid, ex.version)
        if not ping_show(ex.server):
            log.info("기존 인스턴스가 응답하지 않습니다 (구버전일 수 있음)")
        return "exit"

    log.info("구버전(pid=%s, %s)을 종료하고 %s 로 이어받습니다", ex.pid, ex.version, version)
    ping_quit(ex.server)
    time.sleep(0.6)
    terminate(ex.pid)
    write_lock(version)
    return "run"
