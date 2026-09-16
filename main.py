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


def use_os_trust_store() -> bool:
    """학교망 SSL 검사 장비(#63) 대응: 인증서 검증에 번들 certifi 대신 OS 저장소를 쓴다.

    학교 PC 는 검사 장비의 CA 가 Windows 저장소/Keychain 에만 설치돼 있어,
    certifi 만 보는 얼린 앱은 구글 로그인 등 모든 HTTPS 가 실패한다.
    """
    try:
        import truststore

        truststore.inject_into_ssl()
        return True
    except Exception as e:  # noqa: BLE001 - 실패해도 certifi 로 동작은 한다
        print(f"[catmoa] OS 인증서 저장소 사용 불가(certifi 로 동작): {e}", file=sys.stderr)
        return False


def selftest() -> int:
    """`catmoa --selftest` — 화면 없이 상태만 찍는다 (배포판 점검·문의 대응용)."""
    from src import __version__
    from src import config as cfg
    from src.privacy import mask_text, strong

    print(f"catmoa {__version__}  (frozen={getattr(sys, 'frozen', False)})")
    import ssl

    os_trust = getattr(ssl.SSLContext, "__module__", "").startswith("truststore")
    print(f"인증서 검증      : {'OS 저장소 (truststore)' if os_trust else '번들 certifi'}")
    print(f"설정 폴더        : {cfg.config_dir()}")
    print(f"모델 실행기      : {'있음' if strong.runtime_available() else '없음'} (onnxruntime + tokenizers)")
    print(f"강력한 마스킹 모델: {strong.status_line()}")
    sample = "담임 김민수 선생님께. 학생 박서연(010-1234-5678) 상담은 6/10 14:00."
    r = mask_text(sample, strong=strong.is_installed())
    print(f"마스킹 시험       : {r.count}곳 ({r.summary()}) · {'규칙+모델' if r.used_model else '규칙'}")
    print(f"  {r.masked}")
    return 0


def main() -> int:
    use_os_trust_store()
    if "--selftest" in sys.argv:
        return selftest()
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

    from src import single_instance as si

    if si.take_over() == "exit":
        # 이미 같은/최신 버전이 떠 있다 — 그 고양이를 보여주고 조용히 빠진다
        print("[catmoa] 이미 실행 중입니다. 떠 있는 고양이를 보여줍니다.")
        return 0

    from src.ui.main_window import create_main_widget

    widget = create_main_widget()
    ctrl = widget._controller
    server = si.InstanceServer(on_show=ctrl.bring_to_front, on_quit=ctrl.quit)
    app.aboutToQuit.connect(si.clear_lock)
    widget.show()
    try:
        return app.exec()
    finally:
        server.close()


if __name__ == "__main__":
    raise SystemExit(main())
