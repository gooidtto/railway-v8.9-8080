import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "platform_capabilities.py"


def run_report(**env):
    merged = os.environ.copy()
    merged.update(env)
    return json.loads(subprocess.check_output([sys.executable, str(SCRIPT)], env=merged, text=True))


def test_railway_tcp_proxy_never_advertises_h3():
    report = run_report(
        RAILWAY_TCP_PROXY_PORT="45959",
        RAILWAY_TCP_APPLICATION_PORT="8080",
        GATEWAY_PORT="8080",
        XRAY_VERSION="26.3.27",
    )
    assert report["railway_tcp_proxy"]["transport"] == "tcp"
    assert report["railway_tcp_proxy"]["http3_quic"] is False
    assert report["xhttp"]["h3_capable_in_xray"] is True
    assert report["xhttp"]["h3_via_current_tcp_proxy"] is False
    assert report["policy"]["advertise_h3_tcp_proxy"] is False


def test_gateway_port_is_8080_by_default(monkeypatch):
    monkeypatch.delenv("GATEWAY_PORT", raising=False)
    monkeypatch.delenv("PORT", raising=False)
    report = run_report()
    assert report["gateway_port"] == 8080
