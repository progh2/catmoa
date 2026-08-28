"""공통 스타일 상수."""

FONT_FAMILY = "Apple SD Gothic Neo, Malgun Gothic, Noto Sans CJK KR, sans-serif"
MONO_FAMILY = "Menlo, Consolas, D2Coding, monospace"

# 고양이 텍스트 표정 (상태별)
CAT_FACES = {
    "idle": "(=^･ω･^=)",
    "hover": "(=^･ω･^=)/",
    "thinking": "(=^･ｰ･^=)?",
    "eating": "(=^･ω･^=)🍙",
    "happy": "(=^◡ω◡^=)♪",
    "error": "(=×ω×=;)",
    "sleeping": "(=^ｰωｰ^=)zzZ",
}

WIDGET_QSS = f"""
QLabel#catFace {{
    font-family: {MONO_FAMILY};
    font-size: 22px;
    color: #333;
    background: rgba(255, 250, 240, 235);
    border: 2px solid #f0c27b;
    border-radius: 16px;
    padding: 10px 14px;
}}
"""
