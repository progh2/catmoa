"""PC 시계 오차 검출 + SSL 실패 힌트 (#64)."""
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import httpx
import pytest

from src import netdiag


def _mock_get(offset: timedelta):
    """서버 시각이 로컬보다 offset 만큼 앞선 응답을 돌려주는 httpx.get 대체."""

    def get(url, **kw):
        date = format_datetime(datetime.now(timezone.utc) + offset, usegmt=True)
        return httpx.Response(204, headers={"Date": date}, request=httpx.Request("GET", url))

    return get


def test_clock_skew_near_zero(monkeypatch):
    monkeypatch.setattr(httpx, "get", _mock_get(timedelta(0)))
    skew = netdiag.clock_skew_seconds()
    assert skew is not None and abs(skew) < 5


def test_clock_skew_slow_clock(monkeypatch):
    # 서버가 30분 앞 = 로컬 시계가 30분 느림 → skew 음수
    monkeypatch.setattr(httpx, "get", _mock_get(timedelta(minutes=30)))
    skew = netdiag.clock_skew_seconds()
    assert skew is not None and -1810 < skew < -1790


def test_clock_skew_offline(monkeypatch):
    def boom(url, **kw):
        raise httpx.ConnectError("no network")

    monkeypatch.setattr(httpx, "get", boom)
    assert netdiag.clock_skew_seconds() is None
    assert "확인 불가" in netdiag.describe_clock(None)


@pytest.mark.parametrize(
    "skew, needle",
    [(3.0, "정상"), (-1800.0, "느립니다"), (1800.0, "빠릅니다")],
)
def test_describe_clock(skew, needle):
    assert needle in netdiag.describe_clock(skew)


def test_ssl_hint_clock(monkeypatch):
    monkeypatch.setattr(netdiag, "clock_skew_seconds", lambda **kw: -1800.0)
    hint = netdiag.ssl_failure_hint("[SSL: CERTIFICATE_VERIFY_FAILED] ...")
    assert "PC 시계" in hint and "느립니다" in hint


def test_ssl_hint_intercept(monkeypatch):
    monkeypatch.setattr(netdiag, "clock_skew_seconds", lambda **kw: 1.0)
    hint = netdiag.ssl_failure_hint("[SSL: CERTIFICATE_VERIFY_FAILED] self-signed certificate")
    assert "보안 장비" in hint


def test_ssl_hint_not_ssl():
    assert netdiag.ssl_failure_hint("Connection timed out") == ""
