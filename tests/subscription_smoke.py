import base64
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / "scripts" / "generate.py"

BASE = {
    "UUID": "11111111-1111-4111-8111-111111111111",
    "PRIVATE_KEY": "test-private-key",
    "PUBLIC_KEY": "test-public-key",
    "VLESS_DECRYPTION": "test-decryption",
    "VLESS_ENCRYPTION": "test-encryption",
    "XHTTP_PATH": "/xhttp",
    "XHTTP_MODE": "auto",
    "SHORT_ID": "50175c035ee132",
}


def run_generate(*, public_domain="", host="", port=""):
    with tempfile.TemporaryDirectory() as td:
        data = Path(td) / "data"
        config = Path(td) / "etc" / "xray" / "config.json"
        env = os.environ.copy()
        env.update(BASE)
        env.update(
            DATA_DIR=str(data),
            CONFIG=str(config),
            RAILWAY_PUBLIC_DOMAIN=public_domain,
            SERVER_HOST=host,
            SERVER_PORT=port,
            SUBSCRIPTION_TOKEN="smoke-token",
        )
        proc = subprocess.run(
            [sys.executable, str(GEN)],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
        )
        files = {}
        if data.exists():
            for p in data.iterdir():
                if p.is_file():
                    files[p.name] = p.read_text()
        return proc, files


def lines(files):
    return [x for x in files.get("vless.txt", "").splitlines() if x.strip()]


def main():
    # HTTPS-only mode: no TCP/REALITY endpoint may be advertised.
    p, f = run_generate(public_domain="demo.example.com")
    assert p.returncode == 0, p.stderr
    ns = lines(f)
    assert len(ns) == 1 and "security=tls" in ns[0], ns
    assert "security=reality" not in ns[0], ns

    # TCP-only mode: REALITY endpoint must be present.
    p, f = run_generate(host="tcp.example.com", port="12345")
    assert p.returncode == 0, p.stderr
    ns = lines(f)
    assert len(ns) == 1 and "security=reality" in ns[0], ns

    # Dual mode: both endpoints are valid and ordered HTTPS first.
    p, f = run_generate(public_domain="demo.example.com", host="tcp.example.com", port="12345")
    assert p.returncode == 0, p.stderr
    ns = lines(f)
    assert len(ns) == 2, ns
    assert "security=tls" in ns[0] and "security=reality" in ns[1], ns

    client = json.loads(f["client.json"])
    outbounds = client["outbounds"]
    assert len(outbounds) == 2, outbounds
    reality = outbounds[1]["streamSettings"]["realitySettings"]
    assert reality["publicKey"] == BASE["PUBLIC_KEY"], reality
    assert "password" not in reality, reality

    # Whitespace around externally injected TCP values must not create bad URIs.
    p, f = run_generate(host="  tcp.example.com  ", port=" 12345 ")
    assert p.returncode == 0, p.stderr
    assert "@tcp.example.com:12345/" in lines(f)[0], lines(f)

    # No usable public endpoint must fail closed.
    p, _ = run_generate()
    assert p.returncode != 0
    assert "no usable public subscription endpoint" in p.stderr or "no usable public subscription endpoint" in p.stdout

    # Subscription must be valid base64 and decode to the exact node list.
    p, f = run_generate(public_domain="demo.example.com", host="tcp.example.com", port="12345")
    assert p.returncode == 0, p.stderr
    decoded = base64.b64decode(f["subscription.txt"]).decode()
    assert decoded.strip() == f["vless.txt"].strip(), (decoded, f["vless.txt"])

    print("subscription smoke tests: PASS")


if __name__ == "__main__":
    main()
