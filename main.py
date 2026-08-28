"""catmoa 진입점.

플로팅 고양이 위젯을 띄운다. 고양이 위젯(#8)이 구현되기 전까지는
플레이스홀더 창을 표시한다.
"""
from __future__ import annotations

import sys


def main() -> int:
    from PySide6.QtWidgets import QApplication

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
