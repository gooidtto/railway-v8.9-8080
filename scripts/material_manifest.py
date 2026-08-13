#!/usr/bin/env python3
"""Persist non-secret fingerprints for restart/migration consistency.

Secret values are never written to the manifest. The manifest lets a new
container prove that UUID, REALITY public key, and VLESS ML-KEM material were
loaded from the same persistent volume without exposing the material itself.
"""
import hashlib
import json
import os
from pathlib import Path

SCHEMA_VERSION = 1


def read(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def main() -> None:
    data_dir = Path(read("DATA_DIR", "/data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    material = {
        "uuid": read("UUID"),
        "public_key": read("PUBLIC_KEY"),
        "vless_decryption": read("VLESS_DECRYPTION"),
        "vless_encryption": read("VLESS_ENCRYPTION"),
        "short_id": read("SHORT_ID"),
    }
    if not all(material.values()):
        raise SystemExit("ERROR: cannot write material manifest with incomplete material")

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "algorithm": "sha256",
        "material": {key: digest(value) for key, value in material.items()},
        "transport": {
            "gateway_port": int(read("GATEWAY_PORT", read("PORT", "8080"))),
            "xray_port": int(read("XRAY_PORT", "10087")),
            "xray_http_port": int(read("XRAY_HTTP_PORT", "10086")),
            "xhttp_path": read("XHTTP_PATH", "/xhttp"),
            "xhttp_mode": read("XHTTP_MODE", "auto"),
        },
    }
    target = data_dir / "material-manifest.json"
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, target)
    print(f"material manifest: {target}")


if __name__ == "__main__":
    main()
