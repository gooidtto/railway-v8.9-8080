import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("health_proxy", ROOT / "scripts" / "health_proxy.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_tls_without_proxy_header():
    data = b"\x16\x03\x01\x00\x10" + b"x" * 20
    stripped, pending = MODULE._strip_proxy_header(data)
    assert not pending
    assert stripped == data
    assert MODULE.is_tls(stripped)


def test_proxy_v1_header_is_removed():
    tls = b"\x16\x03\x01\x00\x10" + b"x" * 20
    data = b"PROXY TCP4 203.0.113.10 198.51.100.10 54321 443\r\n" + tls
    stripped, pending = MODULE._strip_proxy_header(data)
    assert not pending
    assert stripped == tls
    assert MODULE.is_tls(stripped)


def test_proxy_v2_header_is_removed():
    tls = b"\x16\x03\x01\x00\x10" + b"x" * 20
    # PROXY v2 signature + version/command + family/protocol + address length.
    header = MODULE.PROXY_V2_SIGNATURE + bytes([0x21, 0x11]) + (12).to_bytes(2, "big")
    header += b"\xcb\x00\x71\x0a\xc6\x33\x64\x0a\xd4\x31\x01\xbb"
    data = header + tls
    stripped, pending = MODULE._strip_proxy_header(data)
    assert not pending
    assert stripped == tls
    assert MODULE.is_tls(stripped)


def test_http_is_not_treated_as_tls():
    data = b"GET /health HTTP/1.1\r\nHost: example.test\r\n\r\n"
    assert MODULE.parse_http(data) == ("GET", "/health")
    assert not MODULE.is_tls(data)
