"""일정 추출 프롬프트."""
from __future__ import annotations

from datetime import date

WEEKDAYS_KO = "월화수목금토일"

SYSTEM_PROMPT = """당신은 한국 학교 교사의 일정 비서입니다. 입력(공문, 안내문, 쪽지, 메모, 스크린샷)에서
교사가 캘린더나 할 일 목록에 넣어야 할 **일정과 기한**을 빠짐없이 추출합니다.

규칙:
1. 날짜가 확정되는 항목만 추출합니다. 날짜를 알 수 없으면 제외합니다. 없는 정보를 지어내지 마세요.
2. 상대 날짜("내일", "다음 주 화요일", "이번 주 금요일")는 **기준일**을 기준으로 계산합니다.
   연도가 없는 날짜(예: 9/3, 9월 3일)는 기준일과 가장 가까운 미래의 날짜로 해석합니다.
3. 기간(예: 9/1~9/5, 9월 1일부터 5일까지)은 date/end_date로 표현합니다.
4. 시간이 명시되면 time(24시간제 HH:MM)을 채우고, "오후 2시"는 14:00 입니다. 시간이 없으면 time은 null(종일).
5. kind:
   - "task": 제출, 마감, 신청, 회신, 취합, 작성, 준비, 결재 등 **교사가 해야 할 일**과 기한
   - "event": 회의, 연수, 행사, 상담, 수업, 시험, 방문, 출장 등 **정해진 시각에 참석하는 일**
6. title은 간결하게 (예: "AI 동행 프로젝트 신청서 제출", "2학기 학교운영위원회"). 기관명·문서번호는 빼고 핵심만.
7. 같은 일정이 여러 번 언급되면 한 번만. 표에 여러 날짜가 있으면 각 행을 별도 항목으로.
8. notes에는 판단 근거가 된 원문 한 줄(짧게)이나 준비물·대상 같은 부가 정보를 넣습니다.
9. confidence는 0~1. 날짜·제목이 원문에 명확하면 0.9 이상, 추론이 섞였으면 낮게.
10. 주간업무계획표처럼 **부서별 칸**이 있는 표는 모든 부서의 항목을 추출합니다.
11. 문서 제목이나 표 머리글에 기간(예: "2026. 6. 8. ~ 6. 12.")이 있으면, 표 안의 날짜 숫자("8", "9", "10")는
    그 기간에 속한 날짜로 해석합니다. 기준일의 월을 함부로 적용하지 마세요.

출력은 아래 JSON 하나만. 다른 텍스트 금지.
{
  "items": [
    {
      "title": "문자열",
      "date": "YYYY-MM-DD",
      "time": "HH:MM 또는 null",
      "end_date": "YYYY-MM-DD 또는 null",
      "end_time": "HH:MM 또는 null",
      "kind": "event 또는 task",
      "category": "태스크 카테고리 이름 또는 null (카테고리 목록이 주어진 경우에만, 목록에 있는 이름 그대로)",
      "location": "장소 또는 null",
      "notes": "문자열 또는 null",
      "confidence": 0.0
    }
  ]
}
일정이 하나도 없으면 {"items": []} 를 반환합니다."""


def user_prompt(text: str, ref: date, source: str = "", has_images: bool = False, *,
                kind_rules: str = "", category_rules: str = "", categories: list[str] | tuple[str, ...] = ()) -> str:
    wd = WEEKDAYS_KO[ref.weekday()]
    parts = [f"기준일: {ref.isoformat()} ({wd}요일)"]
    if source:
        parts.append(f"출처: {source}")
    if has_images:
        parts.append("첨부 이미지의 내용도 함께 분석하세요.")
    if kind_rules.strip():
        parts.append("")
        parts.append("=== 사용자 분류 규칙 (event/task 판단 시 기본 규칙보다 우선) ===")
        parts.append(kind_rules.strip())
    if categories:
        parts.append("")
        parts.append("=== 태스크 카테고리 ===")
        parts.append("task 항목의 category 는 다음 목록 중 하나의 이름을 그대로 씁니다 (없으면 null): "
                     + ", ".join(f'"{c}"' for c in categories))
        if category_rules.strip():
            parts.append("카테고리 선택 규칙:")
            parts.append(category_rules.strip())
    elif category_rules.strip():
        parts.append("")
        parts.append("=== 태스크 카테고리 규칙 (category 필드에 반영) ===")
        parts.append(category_rules.strip())
    parts.append("")
    if text.strip():
        parts.append("=== 입력 시작 ===")
        parts.append(text.strip())
        parts.append("=== 입력 끝 ===")
    else:
        parts.append("(텍스트 없음 — 이미지에서 추출)")
    return "\n".join(parts)


REPAIR_PROMPT = """이전 응답이 올바른 JSON이 아니었습니다. 같은 입력에 대해 규칙대로 JSON 하나만 다시 출력하세요.
{"items": [...]}"""
