"""형식·문맥으로 판단되는 개인정보 탐지 규칙 (coolmsg_v6_pipeline rules.py + run_masking.py 의 로컬 규칙 이식).

각 탐지는 {"start", "end", "label", "rule"}. label 은 masker.PLACEHOLDERS 의 키.
"""
from __future__ import annotations

import re
from typing import Any

_SEP = r"[\-.\s_]"
_LB = r"(?<![\d\-._])"
MOBILE = re.compile(rf"{_LB}01[016789]{_SEP}?\d{{3,4}}{_SEP}?\d{{4}}(?!\d)")
LANDLINE = re.compile(rf"{_LB}0(?:2|[3-6][1-5]){_SEP}?\d{{3,4}}{_SEP}?\d{{4}}(?!\d)")
LOCAL_PHONE = re.compile(rf"{_LB}\d{{3,4}}{_SEP}\d{{4}}(?!\d)")
EMAIL = re.compile(r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
DOCUMENT_CODE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]{1,2}\d{8,10}(?![0-9])")
NEIS_ID = re.compile(r"(?<![A-Za-z0-9])[A-Z]\d{9}(?![0-9])")
LICENCE_LIKE = re.compile(r"(?<![A-Za-z0-9])[A-Z]{2}-[A-Z]{3}-\d{4}(?![0-9])")
RRN = re.compile(r"(?<!\d)(\d{6})-([1-4]\d{6})(?!\d)")
IPV4 = re.compile(r"(?<![\d.])((?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(?![\d.])")

# 학급·학번 — 문맥이 있을 때만
TRIPLE = re.compile(r"(?<![\w-])(?P<value>[1-6]\s*[-–]\s*\d{1,2}\s*[-–]\s*\d{1,3})(?![\w-])")
GRADE_CLASS = re.compile(r"(?<!\d)\d{1,2}\s*학년\s*(?P<value>\d{1,2}\s*반)(?![\d급])")
COMPACT_CLASS = re.compile(r"(?<![\w-])(?P<value>[1-6]\s*[-–]\s*\d{1,2}\s*반)(?![\w급-])")
EXPLICIT_NUMBER = re.compile(r"(?:학번|학생번호|출석번호|개인번호|학생\s*번호)\s*[:：]?\s*(?P<value>\d{1,10}(?:\s*번)?)")
NUMBER_UNIT = re.compile(r"(?<!\d)(?P<value>\d{1,3}\s*번)(?![호째지])")
COMPACT = re.compile(r"(?<![\w-])(?P<value>[1-6]\s*[-–]\s*\d{1,2})(?![\w-])")
FIVE_DIGIT = re.compile(r"(?<!\d)(?P<value>[1-6]\d{4})(?!\d)")
ROSTER_HEADER = re.compile(r"학번\s*[\r\n ]+이름\s*[\r\n ]+전화번호")
POSITIVE_CONTEXT = re.compile(r"학생|학생회|학부모|보호자|출석|결석|명단|명렬|학급|반별|담임|상담|수상|시상|대상자|전입|전학|학적|성명|이름|번호|사진|파일|좌석")
STRONG_CONTEXT = re.compile(r"학생|학생증|명단|명렬|출석|결석|담임|학번|학생번호|성명|이름|전입|전학|학적|좌석")
COMPACT_NEGATIVE = re.compile(r"교시|시간표|수업|쪽|페이지|단계|주차|개월|주간|일간|버전|번지|문제|문항|기간|날짜|연도|학기|비율|시작|종료|(?<![가-힣])(?:명|건|원|점|호)(?![가-힣])")
NUMBER_NEGATIVE = re.compile(r"문제|문항|페이지|쪽|회차|번째|차시|번지|단계|교시|시간|(?<![가-힣])(?:호|명|건|원|점)(?![가-힣])")

# 문맥 규칙 (run_masking.local_candidates)
SECRET_RE = re.compile(r"(?:비밀번호|암호|패스워드|인증번호|OTP|API\s*키|토큰)\s*[:=：]?\s*(?P<value>[^\s,;]{4,80})", re.I)
BIRTH_RE = re.compile(r"(?:생년월일|출생일|생일)\s*[:=：]?\s*(?P<value>\d{2,4}[./-]\d{1,2}[./-]\d{1,2}|\d{6,8})")
LABELED_ID_RE = re.compile(r"(?:신청번호|접수번호|사번|학번|학생번호)\s*[:：]?\s*(?P<value>[A-Za-z0-9][A-Za-z0-9_-]{3,39})")
ADDRESS_LINE_RE = re.compile(
    r"(?P<value>(?:서울(?:특별시|시)?|경기도|인천(?:광역시)?|부산(?:광역시)?|대구(?:광역시)?|대전(?:광역시)?|광주(?:광역시)?|울산(?:광역시)?|세종(?:특별자치시)?|강원(?:특별자치도)?|충청[남북]도|전라[남북]도|경상[남북]도|제주(?:특별자치도)?)[^\r\n]{4,100}?\d+(?:-\d+)?(?:\s*\([^\r\n)]{1,30}\))?)")
PRIVATE_URL_HINT = re.compile(r"(?:token|auth|key|password|invite|signature)=|docs\.google\.com|drive\.google\.com|forms\.gle|open\.kakao", re.I)
URL_RE = re.compile(r"https?://[^\s<>'\"]+")
_ROLE_WORD = r"(?:선생님|선생|주무관|선임|부장|교감|교장|담임|교사|주임|과장|팀장|원장|실장|쌤|샘|학생|군|양)"
# '홍길동 부장님', '최유나 교감선생님이' 처럼 직함이 겹쳐 붙는 경우까지 (직함 1~3개 + 조사)
ROLE_NAME_RE = re.compile(
    r"(?<![가-힣])(?P<value>[가-힣]{2,4})"
    rf"(?=\s*{_ROLE_WORD}{{1,3}}(?:께서|님께|님|께|씨|이|은|는|의|과|와|도|에게|한테)?(?![가-힣]))")
LABELED_NAME_RE = re.compile(r"(?:수련지도사|담당자|담당|강사|성명|이름|학생|보호자|학부모|보낸\s*사람|발신자?)[^:\n]{0,18}[:：]\s*\(?\s*(?P<value>[가-힣]{2,4})(?=\s*(?:☎|\d|/|,|\)|\(|$|\s))")
SELF_NAME_RE = re.compile(r"저\((?P<value>[가-힣]{2,4})\)")
CONTACT_NAME_RE = re.compile(r"(?<![가-힣])(?P<value>[가-힣]{2,4})(?=\s*(?:01[016789]|0\d{1,2}[-.)]|[A-Za-z0-9._%+-]+@))")
NON_PERSON_WORDS = {"담임", "담당", "수련", "지도사", "선생", "선생님", "교직원", "예방교육", "학년부", "교무부", "학생부", "행정실", "교육청",
                    "관리자", "전체", "여러분", "각반", "각학년", "안내", "요청", "회의", "부장님", "학부모", "보호자",
                    # 직함 앞에 흔히 오는 비인명 (학년·교과·부서·수식어)
                    "학년", "모든", "전교", "모든", "해당", "관련", "각각", "신규", "기간제", "전담", "보건", "영양", "사서", "상담",
                    "체육", "음악", "미술", "영어", "수학", "국어", "과학", "사회", "역사", "도덕", "기술", "가정", "정보", "한문",
                    "일본어", "중국어", "진로", "특수", "유치원", "초등", "중등", "고등", "교과", "담임", "부담임", "학급", "교무",
                    "연구", "생활", "안전", "인성", "방과후", "돌봄", "급식", "시설", "교육", "행정", "감사", "존경하는", "친애하는",
                    # 연락처 앞에 흔히 오는 라벨 (이름으로 오인 방지)
                    "연락처", "전화", "전화번호", "휴대폰", "핸드폰", "문의", "문의처", "이메일", "메일", "번호", "대표", "사무실",
                    "긴급", "비상", "내선", "직통", "팩스", "주소", "우리", "저희", "해당반", "우리반", "전교생", "재학생"}
DATE_WITH_HOUR = re.compile(r"20\d{2}-\d{2}-\d{2}(?:[ T]?\d{1,2})?")


def _add(items: list[dict[str, Any]], start: int, end: int, label: str, rule: str, prio: int = 4) -> None:
    if end > start:
        items.append({"start": start, "end": end, "label": label, "rule": rule, "prio": prio})


def _rrn_valid(value: str) -> bool:
    digits = [int(c) for c in re.sub(r"\D", "", value)]
    if len(digits) != 13:
        return False
    weights = (2, 3, 4, 5, 6, 7, 8, 9, 2, 3, 4, 5)
    return (11 - sum(d * w for d, w in zip(digits[:12], weights)) % 11) % 10 == digits[12]


def structured(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for pat, label, rule in ((DOCUMENT_CODE, "document_id", "document_code"), (NEIS_ID, "document_id", "neis_id"),
                             (LICENCE_LIKE, "document_id", "licence_like"), (MOBILE, "phone", "mobile"),
                             (LANDLINE, "phone", "landline"), (LOCAL_PHONE, "phone", "local_phone"),
                             (EMAIL, "email", "email"), (IPV4, "ip", "ipv4")):
        for m in pat.finditer(text):
            if label == "document_id" and DATE_WITH_HOUR.fullmatch(m.group(0).strip()):
                continue
            _add(out, m.start(), m.end(), label, rule)
    for m in RRN.finditer(text):
        if _rrn_valid(m.group(0)):
            _add(out, m.start(), m.end(), "id", "rrn", 5)
    return out


def class_numbers(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in TRIPLE.finditer(text):
        _add(out, m.start("value"), m.end("value"), "student_number", "triple")
    for pat, rule in ((GRADE_CLASS, "grade_class"), (COMPACT_CLASS, "compact_class")):
        for m in pat.finditer(text):
            _add(out, m.start("value"), m.end("value"), "klass", rule)
    for m in EXPLICIT_NUMBER.finditer(text):
        _add(out, m.start("value"), m.end("value"), "student_number", "explicit_number")
    for m in NUMBER_UNIT.finditer(text):
        s, e = m.start("value"), m.end("value")
        w = text[max(0, s - 34):min(len(text), e + 34)]
        if POSITIVE_CONTEXT.search(w) and not NUMBER_NEGATIVE.search(w):
            _add(out, s, e, "student_number", "number_unit")
    for m in COMPACT.finditer(text):
        s, e = m.start("value"), m.end("value")
        w = text[max(0, s - 34):min(len(text), e + 34)]
        if POSITIVE_CONTEXT.search(w) and not COMPACT_NEGATIVE.search(w):
            _add(out, s, e, "klass", "compact")
    for m in FIVE_DIGIT.finditer(text):
        s, e = m.start("value"), m.end("value")
        if STRONG_CONTEXT.search(text[max(0, s - 34):min(len(text), e + 34)]):
            _add(out, s, e, "student_number", "five_digit")
    return out


def roster(text: str) -> list[dict[str, Any]]:
    if not ROSTER_HEADER.search(text):
        return []
    lines, cursor = [], 0
    for line in text.splitlines(keepends=True):
        lines.append((cursor, line.rstrip("\r\n")))
        cursor += len(line)
    out: list[dict[str, Any]] = []
    for i in range(len(lines) - 2):
        (s1, l1), (s2, l2), (s3, l3) = lines[i], lines[i + 1], lines[i + 2]
        a = re.fullmatch(r"\s*(?P<v>\d{5})\s*", l1)
        b = re.fullmatch(r"\s*(?P<v>[가-힣]{2,4})\s*", l2)
        c = re.fullmatch(r"\s*(?P<v>(?:\d{3,4}[ ._-]?\d{4}|01[016789][ ._-]?\d{3,4}[ ._-]?\d{4}))\s*", l3)
        if a and b and c:
            _add(out, s1 + a.start("v"), s1 + a.end("v"), "student_number", "roster_id", 5)
            _add(out, s2 + b.start("v"), s2 + b.end("v"), "person", "roster_name", 5)
            _add(out, s3 + c.start("v"), s3 + c.end("v"), "phone", "roster_phone", 5)
    return out


def contextual(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for pat, label, rule in ((SECRET_RE, "secret", "secret"), (BIRTH_RE, "birth", "birth"),
                             (LABELED_ID_RE, "document_id", "labeled_id"), (ADDRESS_LINE_RE, "address", "address_line")):
        for m in pat.finditer(text):
            _add(out, m.start("value"), m.end("value"), label, rule)
    for m in URL_RE.finditer(text):
        if PRIVATE_URL_HINT.search(m.group(0)):
            _add(out, m.start(), m.end(), "url", "private_url")
    for pat, rule in ((ROLE_NAME_RE, "name_before_role"), (LABELED_NAME_RE, "labeled_name"),
                      (SELF_NAME_RE, "self_name"), (CONTACT_NAME_RE, "name_before_contact")):
        for m in pat.finditer(text):
            if not _looks_like_name(m.group("value")):
                continue
            _add(out, m.start("value"), m.end("value"), "person", rule, 3)
    return out


_NAME_SUFFIX_RE = re.compile(r"(께서|님께|님|께|씨|이|가|은|는|의|과|와|도|에게|한테)$")
_NOT_NAME_PARTS = ("선생", "학생", "교사", "학년", "담당", "부장", "교감", "교장", "학교", "교육", "부서", "여러분")


def _looks_like_name(value: str) -> bool:
    """직함·조사·호칭이 섞인 단어('선생님께', '학년부장')는 이름이 아니다."""
    if value in NON_PERSON_WORDS:
        return False
    root = _NAME_SUFFIX_RE.sub("", value)
    if not root or root in NON_PERSON_WORDS or len(root) < 2:
        return False
    return not any(p in value for p in _NOT_NAME_PARTS)


def all_rules(text: str) -> list[dict[str, Any]]:
    return structured(text) + class_numbers(text) + roster(text) + contextual(text)
