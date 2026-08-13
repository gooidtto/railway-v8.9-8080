#!/usr/bin/env python3
"""Validate candidate REALITY SNI/target pairs for the development board.

This tool is deliberately offline-from-production: it never edits Xray config,
subscription material, or the production SNI. It checks DNS/TCP/TLS reachability
and certificate SAN coverage for each candidate hostname. A candidate is only
"compatible" when the certificate presented for that hostname contains the
hostname itself. This is necessary but not sufficient for REALITY compatibility.
"""
from __future__ import annotations

import argparse
import json
import socket
import ssl
from pathlib import Path


def load_candidates(path: Path) -> list[str]:
    values = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        value = raw.strip()
        if not value or value.startswith("#"):
            continue
        if value not in values:
            values.append(value)
    return values


def cert_names(cert: dict) -> set[str]:
    names: set[str] = set()
    for kind, value in cert.get("subjectAltName", ()):
        if kind == "DNS":
            names.add(value.lower().rstrip("."))
    return names


def verify_hostname(cert_names_set: set[str], hostname: str) -> bool:
    hostname = hostname.lower().rstrip(".")
    for name in cert_names_set:
        if name == hostname:
            return True
        if name.startswith("*.") and hostname.endswith(name[1:]) and hostname.count(".") == name.count("."):
            return True
    return False


def probe(hostname: str, timeout: float) -> dict:
    result = {"sni": hostname, "dns": False, "tcp443": False, "tls": False, "certificate_covers_sni": False}
    try:
        addresses = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
        result["dns"] = bool(addresses)
    except OSError as exc:
        result["error"] = f"dns: {exc}"
        return result

    context = ssl.create_default_context()
    try:
        with socket.create_connection((hostname, 443), timeout=timeout) as raw:
            result["tcp443"] = True
            with context.wrap_socket(raw, server_hostname=hostname) as tls:
                result["tls"] = True
                cert = tls.getpeercert()
                names = cert_names(cert)
                result["certificate_names"] = sorted(names)
                result["certificate_covers_sni"] = verify_hostname(names, hostname)
                result["tls_version"] = tls.version()
                result["alpn"] = tls.selected_alpn_protocol()
    except (OSError, ssl.SSLError) as exc:
        result["error"] = f"tls: {exc}"
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="config/reality-sni-candidates.txt")
    parser.add_argument("--output", default="artifacts/reality-sni-report.json")
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args()

    candidates = load_candidates(Path(args.input))
    results = [probe(host, args.timeout) for host in candidates]
    report = {
        "schema_version": 1,
        "purpose": "development-only REALITY SNI candidate screening",
        "production_config_changed": False,
        "candidates": results,
        "note": "TLS certificate coverage is necessary but not sufficient for REALITY compatibility; target/SNI pairing must still be validated with Xray tls ping and a real client.",
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
