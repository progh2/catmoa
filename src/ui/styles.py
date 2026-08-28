"""공통 스타일 상수와 고양이 표정."""

FONT_FAMILY = "Apple SD Gothic Neo, Malgun Gothic, Noto Sans CJK KR, sans-serif"
MONO_FAMILY = "Menlo, Consolas, D2Coding, monospace"

# 상태별 텍스트 표정 — 여러 프레임이면 순환 애니메이션
CAT_FACES: dict[str, list[str]] = {
    "idle":     ["(=^･ω･^=)", "(=^･ω･^=)", "(=^･ω･^=)", "(=^-ω-^=)"],      # 가끔 눈 깜빡
    "hover":    ["(=^･ω･^=)ノ", "(=^･ω･^=)ﾉ"],
    # 마우스 방향을 쳐다보는 호버 (이미지 모드: hover_tl/tr/bl/br.png, 없으면 hover → idle 폴백)
    "hover_tl": ["(=^◔ω･^=)", "(=^◔ω･^=)"],
    "hover_tr": ["(=^･ω◔^=)", "(=^･ω◔^=)"],
    "hover_bl": ["(=^◡ω･^=)", "(=^◡ω･^=)"],
    "hover_br": ["(=^･ω◡^=)", "(=^･ω◡^=)"],
    "drag":     ["(=^ﾟωﾟ^=)!", "(=^ﾟωﾟ^=)!!"],
    "thinking": ["(=^･ｰ･^=)?", "(=^･ｰ･^=)？", "(=^･ｰ･^=)?"],
    "eating":   ["(=^･ω･^=)🍙", "(=^ω^=)🍙", "(=^･ω･^=)🍚", "(=^ω^=) "],
    "happy":    ["(=^◡ω◡^=)♪", "(=^◡ω◡^=)♫"],
    "error":    ["(=×ω×=;)", "(=×ω×=;;)"],
    "annoyed":  ["(=｀ω´=)", "(=｀ω´=)!"],           # 지원하지 않는 입력
    "empty":    ["(=･ω･=)?", "(=･ω･=)…"],            # 일정을 못 찾음
    "searching": ["(=^･ω･^=)🔍", "(=^･ω･^=)📄"],     # 쿨메신저 확인 중
    "bored":    ["(=－ω－=)…", "(=－ω－=) ~"],          # 오래 유휴
    "sleeping": ["(=^ｰωｰ^=)z", "(=^ｰωｰ^=)zz", "(=^ｰωｰ^=)zzZ"],
}

FRAME_MS: dict[str, int] = {
    "idle": 500, "hover": 500, "hover_tl": 800, "hover_tr": 800, "hover_bl": 800, "hover_br": 800, "drag": 300, "thinking": 400,
    "eating": 350, "happy": 400, "error": 500, "annoyed": 500, "empty": 700,
    "searching": 400, "bored": 1200, "sleeping": 800,
}

STATE_TIPS: dict[str, str] = {
    "idle": "파일·이미지·텍스트를 여기에 떨어뜨리거나, 마우스를 올린 채 붙여넣기(⌘V / Ctrl+V)",
    "hover": "붙여넣기: ⌘V / Ctrl+V · 우클릭: 메뉴",
    "hover_tl": "붙여넣기: ⌘V / Ctrl+V · 우클릭: 메뉴",
    "hover_tr": "붙여넣기: ⌘V / Ctrl+V · 우클릭: 메뉴",
    "hover_bl": "붙여넣기: ⌘V / Ctrl+V · 우클릭: 메뉴",
    "hover_br": "붙여넣기: ⌘V / Ctrl+V · 우클릭: 메뉴",
    "drag": "놓으세요!",
    "thinking": "읽는 중…",
    "eating": "분석 중…",
    "happy": "완료!",
    "error": "오류",
    "annoyed": "이건 못 읽어요 (hwp/hwpx/pdf/이미지/텍스트만)",
    "empty": "일정을 찾지 못했어요",
    "searching": "쿨메신저 새 쪽지 찾는 중…",
    "bored": "심심해요… 뭐든 던져주세요",
    "sleeping": "쉬는 중… (마우스를 올리면 깨어나요)",
}

WIDGET_QSS = f"""
QLabel#catFace {{
    color: #3a2e1e;
    background: rgba(255, 250, 240, 240);
    border: 2px solid #f0c27b;
    border-radius: 18px;
    padding: 10px 16px;
}}
QLabel#catFace[state="drag"] {{ border-color: #6fbf73; background: rgba(240, 255, 240, 245); }}
QLabel#catFace[state="eating"], QLabel#catFace[state="thinking"] {{ border-color: #f2a65a; }}
QLabel#catFace[state="happy"] {{ border-color: #6fbf73; }}
QLabel#catFace[state="error"] {{ border-color: #e06666; background: rgba(255, 240, 240, 245); }}
QLabel#catFace[state="sleeping"] {{ color: #8a7d6b; border-color: #d9cdb8; }}
/* 이미지 모드는 상태와 무관하게 투명 — 상태 규칙보다 뒤에 두어 우선 적용 */
QLabel#catFace[mode="image"] {{ background: transparent; border: none; padding: 0; }}
QLabel#updateBadge {{
    font-size: 12px; font-weight: bold; color: white;
    background: #4a90e2; border-radius: 9px; padding: 1px 6px; margin-right: 2px;
}}
QLabel#updateBadge:hover {{ background: #2f6fc0; }}
QLabel#badge {{
    font-family: {FONT_FAMILY}; font-size: 11px; font-weight: bold; color: white;
    background: #f2a65a; border-radius: 9px; padding: 1px 6px;
}}
"""
