"""일정 추출 프롬프트."""
from __future__ import annotations

from datetime import date

WEEKDAYS_KO = "월화수목금토일"

SYSTEM_PROMPT = """당신은 한국 학교 교사의 일정 비서입니다. 입력(공문, 안내문, 쪽지, 메모, 스크린샷)에서
교사가 캘린더나 할 일 목록에 넣어야 할 **일정과 기한**을 빠짐없이 추출합니다.

규칙:
1. 없는 정보를 지어내지 마세요. 일정(event)은 날짜가 확정되는 것만 추출합니다.
   해야 할 일(task)은 날짜·마감이 없어도 추출하되 date 를 null 로 둡니다(마감 없는 할 일). 날짜를 추측하지 마세요.
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
12. 입력이 "[최근 내용]"과 "[이전 대화 (참고용…)]"로 나뉘어 있으면(답장이 쌓인 쪽지) **최근 내용에서만** 일정을 추출합니다.
    이전 대화는 최근 내용이 가리키는 대상("그 회의", "아까 말한 날짜")을 해석할 때만 참고하고,
    이전 대화에만 있는 지나간 일정은 추출하지 않습니다.
13. title 은 사용자가 바로 실행할 수 있는 **행동 문장**(주어 생략)으로 씁니다: "나이스 출결 마감 입력", "학부모 상담 주간 안내문 배부".
    notes 에는 원문을 다시 열지 않아도 되도록 대상·방법·제출처·첨부·준비물 등 실행에 필요한 상세를 담습니다.
14. 한 메시지에 학생 안내, 시스템 입력, 서류 제출처럼 **서로 다른 행동**이 있으면 항목을 분리합니다.
    단계별 마감이 여러 개면 단계마다 별도 task 로 만듭니다 (하나의 마감에 할 일이 여럿이면 하나로 묶어도 됩니다).
15. scope: "사용자 역할"이 주어진 경우 **수신 대상이 누구인지**를 보고 판단합니다.
    - "relevant": 수신 대상이 사용자를 포함 — "전체 교직원", "각 담임", "담임 선생님들께", "교과 담당", 사용자의 학년·교과·부서를 지정
    - "irrelevant": 수신 대상이 **사용자가 아닌 특정 학년·교과·부서·개인으로만 한정** — 예) 사용자가 "2학년 담임"인데
      "3학년 담임 선생님들께", "1학년 부장님께", "체육 교과 선생님께"(사용자는 정보 교과), "교무부 선생님만"
      → 사용자가 할 일이 없으므로 irrelevant. 다른 학년의 공지라도 "참고하세요"뿐이면 irrelevant.
    - "ambiguous": 대상이 명시되지 않고 사용자 해당 여부를 알 수 없을 때
    수신자 이름이 [이름]처럼 마스킹됐다는 이유만으로 irrelevant 로 판단하지 않습니다. 역할이 없으면 "relevant".
    scope_reason 에 "수신 대상: … / 사용자: …" 형식으로 한 문장. irrelevant 여도 items 는 평소대로 추출합니다(코드가 처리).

출력은 아래 JSON 하나만. 다른 텍스트 금지.
{
  "scope": "relevant 또는 irrelevant 또는 ambiguous",
  "scope_reason": "한 문장",
  "items": [
    {
      "title": "문자열",
      "date": "YYYY-MM-DD (task 이고 날짜가 없으면 null)",
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
일정이 하나도 없으면 "items": [] 로 반환합니다."""


def calendar_hint(ref: date) -> str:
    """상대 날짜 계산을 돕는 3주치 달력 (작은 모델이 '다음 주 목요일'을 틀리지 않게)."""
    from datetime import timedelta

    monday = ref - timedelta(days=ref.weekday())
    rows = []
    for w, label in enumerate(("이번 주", "다음 주", "다다음 주")):
        days = [monday + timedelta(days=7 * w + i) for i in range(7)]
        rows.append(f"{label}: " + " ".join(f"{d:%m/%d}({WEEKDAYS_KO[d.weekday()]})" for d in days))
    # 상대 표현 → 날짜 직접 대응표 (계산 실수 방지). "다음 주 X요일" 은 기준일 다음 주의 해당 요일.
    rel = [f"내일={ref + timedelta(days=1):%m/%d}", f"모레={ref + timedelta(days=2):%m/%d}"]
    for w, label in ((0, "이번 주"), (1, "다음 주")):
        rel.append(label + " " + " ".join(
            f"{WEEKDAYS_KO[i]}={monday + timedelta(days=7 * w + i):%m/%d}" for i in range(7)))
    return ("날짜 참고 (기준일이 속한 주부터) — " + " / ".join(rows)
            + "\n상대 표현 대응표: " + "; ".join(rel))


def user_prompt(text: str, ref: date, source: str = "", has_images: bool = False, *,
                kind_rules: str = "", category_rules: str = "", categories: list[str] | tuple[str, ...] = (),
                persona: str = "") -> str:
    wd = WEEKDAYS_KO[ref.weekday()]
    parts = [f"기준일: {ref.isoformat()} ({wd}요일)", calendar_hint(ref)]
    if source:
        parts.append(f"출처: {source}")
    if persona.strip():
        parts.append("")
        parts.append("=== 사용자 역할 (scope 판단 기준) ===")
        parts.append(persona.strip())
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
