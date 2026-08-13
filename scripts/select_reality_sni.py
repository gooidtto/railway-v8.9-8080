"""Select a validated REALITY SNI for development deployments.

Production remains static unless REALITY_SNI_MODE=random is explicitly set.
The selector never treats the candidate list as proof of REALITY compatibility;
validation is intentionally conservative and the selected value is recorded.
"""
import os
import random
import socket
from pathlib import Path

DEFAULT_CANDIDATES = [
    "www.cloudflare.com",
    "www.microsoft.com",
    "www.bing.com",
    "www.apple.com",
]


def candidate_list(path: str | None = None) -> list[str]:
    p = Path(path or os.getenv("REALITY_SNI_CANDIDATES_FILE", "config/reality-sni-candidates.txt"))
    if not p.exists():
        return DEFAULT_CANDIDATES.copy()
    values = []
    for raw in p.read_text(encoding="utf-8").splitlines():
        value = raw.strip()
        if value and not value.startswith("#") and value not in values:
            values.append(value)
    return values


def basic_dns_candidates(candidates: list[str]) -> list[str]:
    validated = []
    for host in candidates:
        try:
            socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        except OSError:
            continue
        validated.append(host)
    return validated


def select_sni(candidates: list[str], mode: str, fallback: str = "www.cloudflare.com") -> str:
    mode = (mode or "static").strip().lower()
    if mode != "random":
        return fallback
    pool = basic_dns_candidates(candidates)
    if not pool:
        raise RuntimeError("no DNS-valid REALITY SNI candidates")
    return random.choice(pool)


if __name__ == "__main__":
    mode = os.getenv("REALITY_SNI_MODE", "static")
    selected = select_sni(candidate_list(), mode, os.getenv("REALITY_SNI", "www.cloudflare.com"))
    print(selected)
