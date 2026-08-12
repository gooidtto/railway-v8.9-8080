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
xray_http_port = int(env("XRAY_HTTP_PORT", "10086"))
xray_listen = env("XRAY_LISTEN", "0.0.0.0")
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

# Endpoint precedence:
# 1. Explicit XRAY_TCP_PROXY_HOST/PORT (authoritative).
# 2. Explicit SERVER_HOST/SERVER_PORT (compatibility override).
# 3. Railway's injected RAILWAY_TCP_PROXY_DOMAIN/PORT, but only when the
#    target application port is known to be Xray 10085, or when Railway did
#    not expose the target-port metadata at all. This fixes deployments where
#    Railway exposes the public TCP proxy but leaves RAILWAY_TCP_APPLICATION_PORT
#    unset. A known target of 8080 is always rejected for REALITY.
dedicated_host = env("XRAY_TCP_PROXY_HOST", "").strip()
dedicated_port = env("XRAY_TCP_PROXY_PORT", "").strip()
if bool(dedicated_host) != bool(dedicated_port):
    raise SystemExit("ERROR: XRAY_TCP_PROXY_HOST and XRAY_TCP_PROXY_PORT must be set together")
if dedicated_port and (not dedicated_port.isdigit() or not 1 <= int(dedicated_port) <= 65535):
    raise SystemExit("ERROR: XRAY_TCP_PROXY_PORT must be 1-65535")

explicit_host = dedicated_host or env("SERVER_HOST", "").strip()
explicit_port = dedicated_port or env("SERVER_PORT", "").strip()
railway_host = env("RAILWAY_TCP_PROXY_DOMAIN", "").strip()
railway_port = env("RAILWAY_TCP_PROXY_PORT", "").strip()
railway_target_port = env("RAILWAY_TCP_APPLICATION_PORT", "").strip()

host = explicit_host
server_port = explicit_port
endpoint_source = "explicit" if host and server_port else "disabled"

if not (host and server_port) and bool(railway_host) != bool(railway_port):
    raise SystemExit("ERROR: Railway TCP proxy metadata is incomplete: RAILWAY_TCP_PROXY_DOMAIN/PORT must be set together")

if not (host and server_port) and railway_host and railway_port:
    if not railway_port.isdigit() or not 1 <= int(railway_port) <= 65535:
        raise SystemExit("ERROR: RAILWAY_TCP_PROXY_PORT must be 1-65535")
    if railway_target_port == str(xray_port):
        host, server_port, endpoint_source = railway_host, railway_port, "railway-xray-port"
    elif railway_target_port == str(env("PORT", "8080")):
        # A Railway proxy known to target HTTP 8080 is never a REALITY endpoint.
        host, server_port, endpoint_source = "", "", "rejected-http-port"
    elif not railway_target_port:
        # Railway sometimes exposes DOMAIN/PORT but omits APPLICATION_PORT.
        # In the single-service configuration the only acceptable public TCP
        # target is Xray's 10085; use the metadata rather than silently dropping
        # the node from the subscription.
        host, server_port, endpoint_source = railway_host, railway_port, "railway-port-metadata"
    else:
        host, server_port, endpoint_source = "", "", "rejected-unknown-port"

public_domain = env("RAILWAY_PUBLIC_DOMAIN", "").strip()

reality_inbound = {
    "listen": xray_listen,
    "port": xray_port,
    "protocol": "vless",
    "settings": {"clients": [{"id": uuid}], "decryption": vless_decryption},
    "streamSettings": {
        "network": "xhttp", "security": "reality",
        "realitySettings": {"show": False, "target": target, "xver": 0, "serverNames": [sni], "privateKey": private_key, "shortIds": [short_id]},
        "xhttpSettings": {"path": xhttp_path, "mode": xhttp_mode},
    },
}

https_inbound = {
    "listen": "127.0.0.1", "port": xray_http_port, "protocol": "vless",
    "settings": {"clients": [{"id": uuid}], "decryption": vless_decryption},
    "streamSettings": {"network": "xhttp", "security": "none", "xhttpSettings": {"path": xhttp_path, "mode": xhttp_mode}},
}

config = {"log": {"loglevel": env("XRAY_LOGLEVEL", "info")}, "inbounds": [reality_inbound, https_inbound], "outbounds": [{"protocol": "freedom", "tag": "direct"}]}
config_path.parent.mkdir(parents=True, exist_ok=True)
tmp = str(config_path) + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(config, f, indent=2)
    f.write("\n")
os.chmod(tmp, 0o600)
os.replace(tmp, config_path)
data_dir.mkdir(parents=True, exist_ok=True)
os.chmod(data_dir, 0o700)
for filename, value in (("vless_decryption.txt", vless_decryption), ("vless_encryption.txt", vless_encryption)):
    p = data_dir / filename
    tmp = str(p) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(value + "\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, p)

reality_vless = ""
if host and server_port:
    reality_vless = (
        f"vless://{uuid}@{host}:{server_port}/?encryption={quote(vless_encryption, safe='')}"
        f"&security=reality&type=xhttp&fp={quote(fingerprint, safe='')}&sni={quote(sni, safe='')}"
        f"&pbk={quote(public_key, safe='')}&sid={quote(short_id, safe='')}&path={quote(xhttp_path, safe='')}&mode={quote(xhttp_mode, safe='')}"
        "#railway-xhttp-reality-mlkem768"
    )

https_vless = ""
if public_domain:
    https_vless = (
        f"vless://{uuid}@{public_domain}:443/?encryption={quote(vless_encryption, safe='')}"
        f"&security=tls&type=xhttp&fp={quote(fingerprint, safe='')}&sni={quote(public_domain, safe='')}&alpn=h2%2Chttp%2F1.1"
        f"&path={quote(xhttp_path, safe='')}&mode={quote(xhttp_mode, safe='')}#railway-xhttp-https-mlkem768"
    )

nodes = [n for n in (https_vless, reality_vless) if n]
if not nodes:
    raise SystemExit("ERROR: no usable public subscription endpoint; set RAILWAY_PUBLIC_DOMAIN or XRAY_TCP_PROXY_HOST/PORT")
vless = "\n".join(nodes)
(data_dir / "vless.txt").write_text(vless + "\n", encoding="utf-8")
subscription = base64.b64encode((vless + "\n").encode()).decode() + "\n"
(data_dir / "subscription.txt").write_text(subscription, encoding="utf-8")
os.chmod(data_dir / "subscription.txt", 0o600)
if subscription_token and public_domain:
    (data_dir / "subscription_url.txt").write_text(f"https://{public_domain}/sub/{subscription_token}\n", encoding="utf-8")
    os.chmod(data_dir / "subscription_url.txt", 0o600)

client_outbounds = []
if https_vless:
    client_outbounds.append({"protocol":"vless","settings":{"vnext":[{"address":public_domain,"port":443,"users":[{"id":uuid,"encryption":vless_encryption}]}]},"streamSettings":{"network":"xhttp","security":"tls","tlsSettings":{"serverName":public_domain,"fingerprint":fingerprint,"alpn":["h2","http/1.1"]},"xhttpSettings":{"path":xhttp_path,"mode":xhttp_mode}}})
if reality_vless:
    client_outbounds.append({"protocol":"vless","settings":{"vnext":[{"address":host,"port":int(server_port),"users":[{"id":uuid,"encryption":vless_encryption}]}]},"streamSettings":{"network":"xhttp","security":"reality","realitySettings":{"serverName":sni,"fingerprint":fingerprint,"publicKey":public_key,"shortId":short_id},"xhttpSettings":{"path":xhttp_path,"mode":xhttp_mode}}})
client = {"log":{"loglevel":"warning"},"inbounds":[{"listen":"127.0.0.1","port":10808,"protocol":"socks","settings":{"udp":True}}],"outbounds":client_outbounds}
with open(data_dir / "client.json", "w", encoding="utf-8") as f:
    json.dump(client, f, indent=2)
os.chmod(data_dir / "client.json", 0o600)
summary = {"transports":["xhttp-https"] + (["xhttp-reality"] if reality_vless else []),"security":["tls"] + (["reality"] if reality_vless else []),"vless_encryption":"ML-KEM-768","xhttp_path":xhttp_path,"xhttp_mode":xhttp_mode,"sni":sni,"server_host":host or None,"server_port":int(server_port) if server_port else None,"endpoint_source":endpoint_source,"https_fallback_host":public_domain or None,"https_fallback_port":443 if public_domain else None,"xray_listen":xray_listen,"xray_port":xray_port,"xray_http_port":xray_http_port,"subscription_endpoint":"/sub/<token>"}
(data_dir / "server-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
