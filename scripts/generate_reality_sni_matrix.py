"""Expand the development subscription into one REALITY node per allowed SNI.

Used only with REALITY_SNI_SERVER_MODE=multi. The server-side REALITY
serverNames list must be populated by apply_reality_sni_pool.py first.
"""
import base64
import json
import os
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from scripts.select_reality_sni import candidate_list

DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
MODE = os.getenv("REALITY_SNI_SERVER_MODE", "single").strip().lower()

if MODE != "multi":
    raise SystemExit(0)

vless_file = DATA_DIR / "vless.txt"
subscription_file = DATA_DIR / "subscription.txt"
summary_file = DATA_DIR / "server-summary.json"

if not vless_file.exists():
    raise SystemExit("ERROR: vless.txt does not exist")

nodes = [line.strip() for line in vless_file.read_text(encoding="utf-8").splitlines() if line.strip()]
reality_nodes = [node for node in nodes if "security=reality" in node]
if len(reality_nodes) != 1:
    raise SystemExit("ERROR: expected exactly one REALITY node before SNI matrix expansion")

base_node = reality_nodes[0]
parts = urlsplit(base_node)
query = dict(parse_qsl(parts.query, keep_blank_values=True))
if query.get("security") != "reality" or query.get("type") != "xhttp":
    raise SystemExit("ERROR: base REALITY subscription node is not XHTTP/REALITY")

pool = candidate_list()
if not pool:
    raise SystemExit("ERROR: SNI candidate pool is empty")

matrix = []
for sni in pool:
    q = dict(query)
    q["sni"] = sni
    matrix_node = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(q), parts.fragment))
    matrix.append(matrix_node)

# Keep the HTTPS node(s) first, then one REALITY node per candidate SNI.
https_nodes = [node for node in nodes if "security=reality" not in node]
all_nodes = https_nodes + matrix
vless_text = "\n".join(all_nodes) + "\n"
vless_file.write_text(vless_text, encoding="utf-8")
encoded = base64.b64encode(vless_text.encode("utf-8")).decode() + "\n"
subscription_file.write_text(encoded, encoding="utf-8")
os.chmod(subscription_file, 0o600)

if summary_file.exists():
    try:
        summary = json.loads(summary_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        summary = {}
else:
    summary = {}
summary.update({
    "sni_server_mode": "multi",
    "sni_matrix_count": len(matrix),
    "sni_matrix": pool,
    "node_count": len(all_nodes),
    "matrix_note": "Development test subscription: each REALITY node differs only by SNI/serverName.",
})
summary_file.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

print(f"REALITY SNI matrix subscription enabled: {len(matrix)} SNI nodes")
print(f"Subscription total nodes: {len(all_nodes)}")
for index, sni in enumerate(pool, 1):
    print(f"REALITY SNI node {index:02d}: {sni}")
