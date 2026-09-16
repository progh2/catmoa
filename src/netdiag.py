"""네트워크 진단 (#64): PC 시계 오차 검출 + SSL 검증 실패 원인 힌트.

인증서 검증 실패는 (1) 학교망 SSL 검사 장비의 CA 미설치, (2) PC 시계가 크게
틀어진 경우 두 갈래다. HTTPS 는 시계가 틀어지면 그 자체가 실패하므로,
암호화 없는 HTTP 요청의 Date 헤더로 서버 시각을 받아 로컬 시계와 비교한다.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

log = logging.getLogger(__name__)

# 가볍고 어디서나 열리는 비-HTTPS 엔드포인트 (캡티브 포털 감지용 URL 들)
_TIME_URLS = [
    "http://www.gstatic.com/generate_204",
    "http://captive.apple.com/hotspot-detect.html",
]

# 인증서 유효기간 오류가 날 정도면 보통 시간 단위지만, 5분 이상이면 경고할 가치가 있다
CLOCK_SKEW_WARN_SECONDS = 300.0


def clock_skew_seconds(timeout: float = 3.0) -> float | None:
    """로컬 시계 − 서버 시계 (초). 양수면 PC 가 빠르고 음수면 느리다. 확인 불가면 None."""
    import httpx

    for url in _TIME_URLS:
        try:
            r = httpx.get(url, timeout=timeout, follow_redirects=False)
            date = r.headers.get("date")
            if not date:
                continue
            server = parsedate_to_datetime(date)
            return (datetime.now(timezone.utc) - server).total_seconds()
        except Exception as e:  # noqa: BLE001 - 다음 후보로
            log.debug("시계 확인 실패(%s): %s", url, e)
    return None


def describe_clock(skew: float | None) -> str:
    """--selftest 등 사람에게 보여줄 시계 상태 한 줄."""
    if skew is None:
        return "확인 불가 (오프라인?)"
    m, s = divmod(abs(int(skew)), 60)
    amount = f"{m}분 {s}초" if m else f"{s}초"
    if abs(skew) < CLOCK_SKEW_WARN_SECONDS:
        return f"정상 (오차 {amount})"
    return f"⚠ {amount} {'빠릅니다' if skew > 0 else '느립니다'} — Windows 설정 → 시간에서 자동 동기화를 켜세요"


def ssl_failure_hint(error_text: str) -> str:
    """SSL 인증서 검증 실패 메시지에 덧붙일 원인 안내. 해당 없으면 빈 문자열."""
    if "CERTIFICATE_VERIFY_FAILED" not in error_text:
        return ""
    skew = clock_skew_seconds()
    if skew is not None and abs(skew) >= CLOCK_SKEW_WARN_SECONDS:
        return f"\n\n원인일 가능성: PC 시계가 {describe_clock(skew)}"
    return (
        "\n\n원인일 가능성: 이 네트워크(학교망 등)의 보안 장비가 통신을 검사하고 있습니다. "
        "브라우저에서 구글이 경고 없이 열린다면 catmoa 최신 버전으로 업데이트하세요. "
        "브라우저에서도 인증서 경고가 뜬다면 전산 담당자에게 보안 장비 인증서 설치를 요청하세요."
    )
