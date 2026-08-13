#!/usr/bin/env python3
"""Emit a conservative runtime capability report for the Railway deployment.

The report intentionally distinguishes Xray transport capability from what the
current Railway public ingress can actually carry. Railway TCP Proxy is TCP;
QUIC/HTTP3 requires UDP and therefore must not be advertised through it.
"""
import json
import os
import sys


def as_bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def main() -> int:
    xray_version = os.getenv("XRAY_VERSION", "26.3.27")
    gateway_port = int(os.getenv("GATEWAY_PORT", os.getenv("PORT", "8080")))
    tcp_proxy_port = os.getenv("RAILWAY_TCP_PROXY_PORT", "")
    tcp_application_port = os.getenv("RAILWAY_TCP_APPLICATION_PORT", str(gateway_port))
    tcp_application_port = int(tcp_application_port) if str(tcp_application_port).isdigit() else None

    report = {
        "schema_version": 1,
        "xray_version": xray_version,
        "gateway_port": gateway_port,
        "railway_tcp_proxy": {
            "enabled": bool(tcp_proxy_port),
            "public_port": int(tcp_proxy_port) if str(tcp_proxy_port).isdigit() else None,
            "application_port": tcp_application_port,
            "transport": "tcp",
            "http3_quic": False,
        },
        "xhttp": {
            "enabled": True,
            "h3_capable_in_xray": True,
            "h3_via_current_tcp_proxy": False,
            "h3_via_railway_https_edge": "unknown-until-probed",
        },
        "policy": {
            "advertise_h3_tcp_proxy": False,
            "advertise_h3_without_udp_probe": False,
        },
    }

    json.dump(report, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
