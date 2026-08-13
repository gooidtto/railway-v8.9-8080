"""Compatibility post-step for the development SNI matrix.

The primary generator now creates the full SNI subscription directly. This
step remains in start.sh for backward compatibility and is intentionally
idempotent: if the subscription is already expanded, it does nothing.
"""
import os
from pathlib import Path

DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
MODE = os.getenv("REALITY_SNI_SERVER_MODE", "single").strip().lower()
if MODE != "multi":
    raise SystemExit(0)

vless_file = DATA_DIR / "vless.txt"
if not vless_file.exists():
    raise SystemExit("ERROR: vless.txt does not exist")

nodes = [line.strip() for line in vless_file.read_text(encoding="utf-8").splitlines() if line.strip()]
reality_nodes = [node for node in nodes if "security=reality" in node]
if len(reality_nodes) > 1:
    print(f"REALITY SNI matrix already generated: {len(reality_nodes)} nodes")
    print(f"Subscription total nodes: {len(nodes)}")
    raise SystemExit(0)

# If exactly one node is present, the primary generator was not run in the
# new implementation. Fail loudly rather than silently producing an ambiguous
# subscription.
raise SystemExit("ERROR: multi-SNI mode expected the primary generator to emit multiple REALITY nodes")
