"""학교망 SSL 검사 장비 대응(#63) — OS 인증서 저장소 주입."""
import ssl

import main


def test_use_os_trust_store_injects():
    assert main.use_os_trust_store() is True
    assert ssl.SSLContext.__module__.startswith("truststore")


def test_use_os_trust_store_idempotent():
    assert main.use_os_trust_store() is True
    assert main.use_os_trust_store() is True
