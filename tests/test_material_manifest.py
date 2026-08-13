import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "material_manifest.py"


def test_manifest_contains_only_fingerprints(tmp_path):
    env = os.environ.copy()
    env.update(
        {
            "DATA_DIR": str(tmp_path),
            "UUID": "d864cffe-5baa-4a6b-954c-b8346400068b",
            "PUBLIC_KEY": "public-test",
            "VLESS_DECRYPTION": "decrypt-test",
            "VLESS_ENCRYPTION": "encrypt-test",
            "SHORT_ID": "50175c035ee132",
            "GATEWAY_PORT": "8080",
            "XRAY_PORT": "10087",
            "XRAY_HTTP_PORT": "10086",
            "XHTTP_PATH": "/xhttp",
            "XHTTP_MODE": "auto",
        }
    )
    subprocess.check_call([sys.executable, str(SCRIPT)], env=env)
    manifest = json.loads((tmp_path / "material-manifest.json").read_text())

    assert manifest["schema_version"] == 1
    assert manifest["algorithm"] == "sha256"
    assert manifest["material"]["uuid"] == hashlib.sha256(env["UUID"].encode()).hexdigest()
    assert manifest["material"]["public_key"] == hashlib.sha256(env["PUBLIC_KEY"].encode()).hexdigest()
    assert "public-test" not in json.dumps(manifest)
    assert "encrypt-test" not in json.dumps(manifest)
    assert manifest["transport"]["gateway_port"] == 8080
