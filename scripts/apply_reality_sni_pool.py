"""Apply a server-side REALITY SNI allow-list for development testing.

This does not change the client subscription SNI. The generated client keeps the
selected/default SNI, while the server accepts any hostname in the configured
candidate pool. This lets the operator manually edit only serverName/SNI in a
client to test candidates against the same REALITY material and target.
"""
import json
import os
from pathlib import Path

from scripts.select_reality_sni import candidate_list

CONFIG = Path(os.getenv("CONFIG", "/etc/xray/config.json"))
MODE = os.getenv("REALITY_SNI_SERVER_MODE", "single").strip().lower()

if MODE not in {"single", "multi"}:
    raise SystemExit("ERROR: REALITY_SNI_SERVER_MODE must be single or multi")

if MODE == "single":
    raise SystemExit(0)

with CONFIG.open("r", encoding="utf-8") as f:
    config = json.load(f)

pool = candidate_list()
if not pool:
    raise SystemExit("ERROR: REALITY SNI candidate pool is empty")

changed = False
for inbound in config.get("inbounds", []):
    stream = inbound.get("streamSettings", {})
    reality = stream.get("realitySettings")
    if not reality:
        continue
    reality["serverNames"] = pool
    changed = True

if not changed:
    raise SystemExit("ERROR: no REALITY inbound found in generated Xray config")

TMP = str(CONFIG) + ".sni.tmp"
with open(TMP, "w", encoding="utf-8") as f:
    json.dump(config, f, indent=2)
    f.write("\n")
os.chmod(TMP, 0o600)
os.replace(TMP, CONFIG)

print(f"REALITY SNI server pool enabled: {len(pool)} candidates")
for value in pool:
    print(f"REALITY SNI allowed: {value}")
