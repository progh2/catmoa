"""catmoa 진입점.

플로팅 고양이 위젯을 띄운다. 고양이 위젯(#8)이 구현되기 전까지는
플레이스홀더 창을 표시한다.
"""
from __future__ import annotations

import sys


LINUX_DEPS_HINT = (
    "Qt 런타임 라이브러리가 없어 화면을 띄울 수 없습니다. 다음을 설치한 뒤 다시 실행하세요:\n"
    "  Debian/Ubuntu: sudo apt-get install -y libegl1 libgl1 libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 "
    "libxcb-keysyms1 libxcb-shape0 libxcb-xinerama0 libdbus-1-3 libfontconfig1 libglib2.0-0\n"
    "  Fedora: sudo dnf install -y mesa-libEGL mesa-libGL libxkbcommon-x11 xcb-util-cursor xcb-util-wm xcb-util-keysyms\n"
    "또한 X11/Wayland 디스플레이(DISPLAY 또는 WAYLAND_DISPLAY)가 있어야 합니다 — 화면 없는 서버/컨테이너에서는 실행할 수 없습니다."
)


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as e:
        if sys.platform.startswith("linux") and (".so" in str(e) or "lib" in str(e)):
            print(f"[catmoa] {e}\n{LINUX_DEPS_HINT}", file=sys.stderr)
            return 2
        raise

    app = QApplication(sys.argv)
    app.setApplicationName("catmoa")
    app.setOrganizationName("catmoa")
    app.setQuitOnLastWindowClosed(False)

    from src.ui.main_window import create_main_widget

    widget = create_main_widget()
    widget.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
