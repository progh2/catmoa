"""공통 스타일 상수와 고양이 표정."""

FONT_FAMILY = "Apple SD Gothic Neo, Malgun Gothic, Noto Sans CJK KR, sans-serif"
MONO_FAMILY = "Menlo, Consolas, D2Coding, monospace"

# 상태별 텍스트 표정 — 여러 프레임이면 순환 애니메이션
CAT_FACES: dict[str, list[str]] = {
    "idle":     ["(=^･ω･^=)", "(=^･ω･^=)", "(=^･ω･^=)", "(=^-ω-^=)"],      # 가끔 눈 깜빡
    "hover":    ["(=^･ω･^=)ノ", "(=^･ω･^=)ﾉ"],
    "drag":     ["(=^ﾟωﾟ^=)!", "(=^ﾟωﾟ^=)!!"],
    "thinking": ["(=^･ｰ･^=)?", "(=^･ｰ･^=)？", "(=^･ｰ･^=)?"],
    "eating":   ["(=^･ω･^=)🍙", "(=^ω^=)🍙", "(=^･ω･^=)🍚", "(=^ω^=) "],
    "happy":    ["(=^◡ω◡^=)♪", "(=^◡ω◡^=)♫"],
    "error":    ["(=×ω×=;)", "(=×ω×=;;)"],
    "sleeping": ["(=^ｰωｰ^=)z", "(=^ｰωｰ^=)zz", "(=^ｰωｰ^=)zzZ"],
}

FRAME_MS: dict[str, int] = {
    "idle": 900, "hover": 500, "drag": 300, "thinking": 400,
    "eating": 350, "happy": 400, "error": 500, "sleeping": 800,
}

STATE_TIPS: dict[str, str] = {
    "idle": "파일·이미지·텍스트를 여기에 떨어뜨리거나, 마우스를 올린 채 붙여넣기(⌘V / Ctrl+V)",
    "hover": "붙여넣기: ⌘V / Ctrl+V · 우클릭: 메뉴",
    "drag": "놓으세요!",
    "thinking": "읽는 중…",
    "eating": "분석 중…",
    "happy": "완료!",
    "error": "오류",
    "sleeping": "쉬는 중… (마우스를 올리면 깨어나요)",
}

WIDGET_QSS = f"""
QLabel#catFace {{
    font-family: {MONO_FAMILY};
    font-size: 20px;
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
QLabel#gear {{
    font-size: 14px; color: #8a7d6b; background: transparent; padding: 0 2px;
}}
QLabel#gear:hover {{ color: #3a2e1e; }}
QLabel#badge {{
    font-family: {FONT_FAMILY}; font-size: 11px; font-weight: bold; color: white;
    background: #f2a65a; border-radius: 9px; padding: 1px 6px;
}}
"""
