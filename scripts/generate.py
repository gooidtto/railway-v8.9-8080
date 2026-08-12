import base64
import json
import os
import re
from pathlib import Path
from urllib.parse import quote, urlparse


def env(name, default=None, required=False):
    value = os.getenv(name, default)
    if required and not value:
        raise SystemExit(f"ERROR: missing {name}")
    return value


data_dir = Path(env("DATA_DIR", "/data"))
config_path = Path(env("CONFIG", "/etc/xray/config.json"))
xray_port = int(env("XRAY_PORT", "10085"))
uuid = env("UUID", required=True)
private_key = env("PRIVATE_KEY", required=True)
public_key = env("PUBLIC_KEY", required=True)
vless_decryption = env("VLESS_DECRYPTION", required=True)
vless_encryption = env("VLESS_ENCRYPTION", required=True)


def normalize_reality_target(value):
    value = (value or "").strip()
    value = re.sub(r"^\[([^\]]+)\]\([^)]*\)$", r"\1", value)
    if value.startswith(("http://", "https://")):
        parsed = urlparse(value)
        value = parsed.netloc or parsed.path
    value = value.strip().strip("[]").rstrip("/")
    if ":" not in value:
        value += ":443"
    host_part, port_part = value.rsplit(":", 1)
    host_part = host_part.strip().strip("[]")
    if not re.fullmatch(r"[A-Za-z0-9.-]+", host_part):
        raise SystemExit("ERROR: REALITY_TARGET hostname is invalid")
    if not port_part.isdigit() or not 1 <= int(port_part) <= 65535:
        raise SystemExit("ERROR: REALITY_TARGET port is invalid")
    return f"{host_part}:{int(port_part)}"


def normalize_sni(value, fallback):
    value = (value or "").strip()
    value = re.sub(r"^\[([^\]]+)\]\([^)]*\)$", r"\1", value)
    if value.startswith(("http://", "https://")):
        value = urlparse(value).hostname or ""
    value = value.strip().strip("[]").rstrip("/") or fallback
    if not re.fullmatch(r"[A-Za-z0-9.-]+", value):
        raise SystemExit("ERROR: REALITY_SNI hostname is invalid")
    return value


target = normalize_reality_target(env("REALITY_TARGET", "www.cloudflare.com:443"))
sni = normalize_sni(env("REALITY_SNI", target.rsplit(":", 1)[0]), target.rsplit(":", 1)[0])
fingerprint = env("REALITY_FINGERPRINT", "chrome")
xhttp_path = env("XHTTP_PATH", "/xhttp")
xhttp_mode = env("XHTTP_MODE", "auto")
short_id = env("SHORT_ID", "50175c035ee132")
subscription_token = env("SUBSCRIPTION_TOKEN", "")
host = env("SERVER_HOST", "")
server_port = env("SERVER_PORT", "")
no_subscription = "--no-subscription" in os.sys.argv

config = {
    "log": {"loglevel": env("XRAY_LOGLEVEL", "info")},
    "inbounds": [{
        "listen": "127.0.0.1",
        "port": xray_port,
        "protocol": "vless",
        "settings": {
            "clients": [{"id": uuid}],
            "decryption": vless_decryption,
        },
        "streamSettings": {
            "network": "xhttp",
            "security": "reality",
            "realitySettings": {
                "show": False,
                "target": target,
                "xver": 0,
                "serverNames": [sni],
                "privateKey": private_key,
                "shortIds": [short_id],
            },
            "xhttpSettings": {"path": xhttp_path, "mode": xhttp_mode},
        },
    }],
    "outbounds": [{"protocol": "freedom", "tag": "direct"}],
}

config_path.parent.mkdir(parents=True, exist_ok=True)
tmp = str(config_path) + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(config, f, indent=2)
    f.write("\n")
os.chmod(tmp, 0o600)
os.replace(tmp, config_path)

data_dir.mkdir(parents=True, exist_ok=True)
os.chmod(data_dir, 0o700)

for filename, value in (
    ("vless_decryption.txt", vless_decryption),
    ("vless_encryption.txt", vless_encryption),
):
    p = data_dir / filename
    tmp = str(p) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(value + "\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, p)

if not (host and server_port):
    if no_subscription:
        for filename in ("subscription.txt", "vless.txt", "client.json", "subscription_url.txt"):
            (data_dir / filename).unlink(missing_ok=True)
        with open(data_dir / "server-summary.json", "w", encoding="utf-8") as f:
            json.dump({
                "subscription": "unavailable",
                "reason": "Railway TCP Proxy not configured",
                "xray_port": xray_port,
                "vless_encryption": "ML-KEM-768",
            }, f, indent=2)
            f.write("\n")
        raise SystemExit(0)
    raise SystemExit("ERROR: SERVER_HOST/SERVER_PORT are required to generate a client subscription")

vless = (
    f"vless://{uuid}@{host}:{server_port}/?"
    f"encryption={quote(vless_encryption, safe='')}"
    f"&security=reality&type=xhttp&fp={quote(fingerprint, safe='')}"
    f"&sni={quote(sni, safe='')}&pbk={quote(public_key, safe='')}&sid={quote(short_id, safe='')}"
    f"&path={quote(xhttp_path, safe='')}&mode={quote(xhttp_mode, safe='')}"
    f"#railway-xhttp-reality-mlkem768"
)
with open(data_dir / "vless.txt", "w", encoding="utf-8") as f:
    f.write(vless + "\n")

subscription = base64.b64encode((vless + "\n").encode("utf-8")).decode("ascii") + "\n"
with open(data_dir / "subscription.txt", "w", encoding="utf-8") as f:
    f.write(subscription)
os.chmod(data_dir / "subscription.txt", 0o600)

if subscription_token:
    public_domain = env("PUBLIC_DOMAIN", "")
    if public_domain:
        with open(data_dir / "subscription_url.txt", "w", encoding="utf-8") as f:
            f.write(f"https://{public_domain}/sub/{subscription_token}\n")
        os.chmod(data_dir / "subscription_url.txt", 0o600)

client = {
    "log": {"loglevel": "warning"},
    "inbounds": [{"listen": "127.0.0.1", "port": 10808, "protocol": "socks", "settings": {"udp": True}}],
    "outbounds": [{
        "protocol": "vless",
        "settings": {"vnext": [{
            "address": host,
            "port": int(server_port),
            "users": [{"id": uuid, "encryption": vless_encryption}],
        }]},
        "streamSettings": {
            "network": "xhttp",
            "security": "reality",
            "realitySettings": {"serverName": sni, "fingerprint": fingerprint, "password": public_key, "shortId": short_id},
            "xhttpSettings": {"path": xhttp_path, "mode": xhttp_mode},
        },
    }],
}
with open(data_dir / "client.json", "w", encoding="utf-8") as f:
    json.dump(client, f, indent=2)
    f.write("\n")
os.chmod(data_dir / "client.json", 0o600)

summary = {
    "transport": "xhttp",
    "security": "reality",
    "vless_encryption": "ML-KEM-768",
    "xhttp_path": xhttp_path,
    "xhttp_mode": xhttp_mode,
    "sni": sni,
    "server_host": host,
    "server_port": int(server_port),
    "xray_port": xray_port,
    "subscription_file": str(data_dir / "subscription.txt"),
    "subscription_endpoint": "/sub/<token>",
    "subscription_token_persisted": bool(subscription_token),
}
with open(data_dir / "server-summary.json", "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=2)
    f.write("\n")
