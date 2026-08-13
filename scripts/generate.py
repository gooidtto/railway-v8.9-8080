import base64
import json
import os
import re
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse
from scripts.select_reality_sni import candidate_list, select_sni

def env(name, default=None, required=False):
    value = os.getenv(name, default)
    if required and not value:
        raise SystemExit(f"ERROR: missing {name}")
    return value

data_dir = Path(env("DATA_DIR", "/data")); config_path = Path(env("CONFIG", "/etc/xray/config.json"))
xray_port = int(env("XRAY_PORT", "10087")); xray_http_port = int(env("XRAY_HTTP_PORT", "10086")); xray_listen = env("XRAY_LISTEN", "127.0.0.1")
gateway_port = int(env("GATEWAY_PORT", env("PORT", "8080"))); uuid = env("UUID", required=True)
private_key = env("PRIVATE_KEY", required=True); public_key = env("PUBLIC_KEY", required=True)
vless_decryption = env("VLESS_DECRYPTION", required=True); vless_encryption = env("VLESS_ENCRYPTION", required=True)

def normalize_target(value):
    value = (value or "").strip()
    if value.startswith(("http://", "https://")):
        p = urlparse(value); value = p.netloc or p.path
    value = value.strip().strip("[]").rstrip("/")
    if ":" not in value: value += ":443"
    host, port = value.rsplit(":", 1)
    if not re.fullmatch(r"[A-Za-z0-9.-]+", host) or not port.isdigit() or not 1 <= int(port) <= 65535:
        raise SystemExit("ERROR: REALITY_TARGET is invalid")
    return f"{host}:{int(port)}"

def normalize_sni(value, fallback):
    value = (value or "").strip()
    if value.startswith(("http://", "https://")): value = urlparse(value).hostname or ""
    value = value.strip().strip("[]").rstrip("/") or fallback
    if not re.fullmatch(r"[A-Za-z0-9.-]+", value): raise SystemExit("ERROR: REALITY_SNI hostname is invalid")
    return value

target = normalize_target(env("REALITY_TARGET", "www.cloudflare.com:443")); target_host = target.rsplit(":", 1)[0]
configured_sni = normalize_sni(env("REALITY_SNI", target_host), target_host)
fingerprint = env("REALITY_FINGERPRINT", "chrome"); xhttp_path = env("XHTTP_PATH", "/xhttp"); xhttp_mode = env("XHTTP_MODE", "auto")
short_id = env("SHORT_ID", "50175c035ee132"); subscription_token = env("SUBSCRIPTION_TOKEN", "")
sni_mode = env("REALITY_SNI_MODE", "static").strip().lower(); sni_server_mode = env("REALITY_SNI_SERVER_MODE", "single").strip().lower()
if sni_mode not in {"static", "random"}: raise SystemExit("ERROR: REALITY_SNI_MODE must be static or random")
if sni_server_mode not in {"single", "multi"}: raise SystemExit("ERROR: REALITY_SNI_SERVER_MODE must be single or multi")
pool = candidate_list()
if not pool: raise SystemExit("ERROR: REALITY SNI candidate pool is empty")
selected_sni = select_sni(pool, "random", configured_sni) if sni_mode == "random" else configured_sni
server_names = pool if sni_server_mode == "multi" else [selected_sni]

dedicated_host = env("XRAY_TCP_PROXY_HOST", "").strip(); dedicated_port = env("XRAY_TCP_PROXY_PORT", "").strip()
if bool(dedicated_host) != bool(dedicated_port): raise SystemExit("ERROR: XRAY_TCP_PROXY_HOST and XRAY_TCP_PROXY_PORT must be set together")
if dedicated_port and (not dedicated_port.isdigit() or not 1 <= int(dedicated_port) <= 65535): raise SystemExit("ERROR: XRAY_TCP_PROXY_PORT must be 1-65535")
explicit_host = dedicated_host or env("SERVER_HOST", "").strip(); explicit_port = dedicated_port or env("SERVER_PORT", "").strip()
railway_host = env("RAILWAY_TCP_PROXY_DOMAIN", "").strip(); railway_port = env("RAILWAY_TCP_PROXY_PORT", "").strip(); railway_target_port = env("RAILWAY_TCP_APPLICATION_PORT", "").strip()
host, server_port = explicit_host, explicit_port; endpoint_source = "explicit" if host and server_port else "disabled"
if not (host and server_port) and bool(railway_host) != bool(railway_port): raise SystemExit("ERROR: Railway TCP proxy metadata is incomplete")
if not (host and server_port) and railway_host and railway_port:
    if not railway_port.isdigit() or not 1 <= int(railway_port) <= 65535: raise SystemExit("ERROR: RAILWAY_TCP_PROXY_PORT must be 1-65535")
    if railway_target_port in {"", str(gateway_port)}: host, server_port, endpoint_source = railway_host, railway_port, "railway-gateway-port" if railway_target_port else "railway-port-metadata"
    elif railway_target_port == str(xray_port): host, server_port, endpoint_source = railway_host, railway_port, "railway-xray-port"
public_domain = env("RAILWAY_PUBLIC_DOMAIN", "").strip()

reality_inbound = {"listen": xray_listen, "port": xray_port, "protocol": "vless", "settings": {"clients": [{"id": uuid}], "decryption": vless_decryption}, "streamSettings": {"network": "xhttp", "security": "reality", "realitySettings": {"show": False, "target": target, "xver": 0, "serverNames": server_names, "privateKey": private_key, "shortIds": [short_id]}, "xhttpSettings": {"path": xhttp_path, "mode": xhttp_mode}}}
https_inbound = {"listen": "127.0.0.1", "port": xray_http_port, "protocol": "vless", "settings": {"clients": [{"id": uuid}], "decryption": vless_decryption}, "streamSettings": {"network": "xhttp", "security": "none", "xhttpSettings": {"path": xhttp_path, "mode": xhttp_mode}}}
config = {"log": {"loglevel": env("XRAY_LOGLEVEL", "info")}, "inbounds": [reality_inbound, https_inbound], "outbounds": [{"protocol": "freedom", "tag": "direct"}]}
config_path.parent.mkdir(parents=True, exist_ok=True); tmp = str(config_path) + ".tmp"
with open(tmp, "w", encoding="utf-8") as f: json.dump(config, f, indent=2); f.write("\n")
os.chmod(tmp, 0o600); os.replace(tmp, config_path); data_dir.mkdir(parents=True, exist_ok=True); os.chmod(data_dir, 0o700)
for filename, value in (("vless_decryption.txt", vless_decryption), ("vless_encryption.txt", vless_encryption)):
    p = data_dir / filename; t = str(p) + ".tmp"
    with open(t, "w", encoding="utf-8") as f: f.write(value + "\n")
    os.chmod(t, 0o600); os.replace(t, p)

def make_reality_node(sni):
    if not (host and server_port): return ""
    return (f"vless://{uuid}@{host}:{server_port}/?encryption={quote(vless_encryption, safe='')}&security=reality&type=xhttp&fp={quote(fingerprint, safe='')}&sni={quote(sni, safe='')}&pbk={quote(public_key, safe='')}&sid={quote(short_id, safe='')}&path={quote(xhttp_path, safe='')}&mode={quote(xhttp_mode, safe='')}#railway-xhttp-reality-mlkem768")

def make_https_node():
    if not public_domain: return ""
    return (f"vless://{uuid}@{public_domain}:443/?encryption={quote(vless_encryption, safe='')}&security=tls&type=xhttp&fp={quote(fingerprint, safe='')}&sni={quote(public_domain, safe='')}&alpn=h2%2Chttp%2F1.1&path={quote(xhttp_path, safe='')}&mode={quote(xhttp_mode, safe='')}#railway-xhttp-https-mlkem768")

https_vless = make_https_node(); reality_nodes = [make_reality_node(s) for s in (pool if sni_server_mode == "multi" else [selected_sni])]; reality_nodes = [n for n in reality_nodes if n]
nodes = ([https_vless] if https_vless else []) + reality_nodes
if not nodes: raise SystemExit("ERROR: no usable public subscription endpoint")
for node in nodes:
    parsed = urlparse(node); q = parse_qs(parsed.query, keep_blank_values=True)
    if parsed.scheme != "vless" or parsed.username != uuid or q.get("encryption", [""])[0] != vless_encryption: raise SystemExit("ERROR: generated VLESS node material mismatch")
    if q.get("security", [""])[0] == "reality" and q.get("type", [""])[0] != "xhttp": raise SystemExit("ERROR: generated REALITY node transport mismatch")

vless_text = "\n".join(nodes) + "\n"; (data_dir / "vless.txt").write_text(vless_text, encoding="utf-8"); (data_dir / "subscription.txt").write_text(base64.b64encode(vless_text.encode()).decode() + "\n", encoding="utf-8"); os.chmod(data_dir / "subscription.txt", 0o600)
if subscription_token and public_domain: (data_dir / "subscription_url.txt").write_text(f"https://{public_domain}/sub/{subscription_token}\n", encoding="utf-8")

client_outbounds = []
if https_vless:
    client_outbounds.append({"protocol":"vless","settings":{"vnext":[{"address":public_domain,"port":443,"users":[{"id":uuid,"encryption":vless_encryption}]}]},"streamSettings":{"network":"xhttp","security":"tls","tlsSettings":{"serverName":public_domain,"fingerprint":fingerprint,"alpn":["h2","http/1.1"]},"xhttpSettings":{"path":xhttp_path,"mode":xhttp_mode}}})
if host and server_port:
    client_outbounds.append({"protocol":"vless","settings":{"vnext":[{"address":host,"port":int(server_port),"users":[{"id":uuid,"encryption":vless_encryption}]}]},"streamSettings":{"network":"xhttp","security":"reality","realitySettings":{"serverName":selected_sni,"fingerprint":fingerprint,"publicKey":public_key,"shortId":short_id},"xhttpSettings":{"path":xhttp_path,"mode":xhttp_mode}}})
with open(data_dir / "client.json", "w", encoding="utf-8") as f: json.dump({"log":{"loglevel":"warning"},"inbounds":[{"listen":"127.0.0.1","port":10808,"protocol":"socks","settings":{"udp":True}}],"outbounds":client_outbounds}, f, indent=2)
os.chmod(data_dir / "client.json", 0o600); (data_dir / "reality-selected-sni.txt").write_text(selected_sni + "\n", encoding="utf-8")
summary = {"transports":["xhttp-https"] + (["xhttp-reality"] if host and server_port else []), "security":["tls"] + (["reality"] if host and server_port else []), "vless_encryption":"ML-KEM-768", "xhttp_path":xhttp_path, "xhttp_mode":xhttp_mode, "sni":selected_sni, "sni_mode":sni_mode, "sni_server_mode":sni_server_mode, "sni_server_names":server_names, "server_host":host or None, "server_port":int(server_port) if server_port else None, "endpoint_source":endpoint_source, "gateway_port":gateway_port, "xray_port":xray_port, "xray_http_port":xray_http_port, "https_fallback_host":public_domain or None, "node_count":len(nodes), "reality_node_count":len(reality_nodes), "material_consistency":"validated"}
(data_dir / "server-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
print(f"REALITY SNI selected: {selected_sni} (mode={sni_mode})")
print(f"REALITY SNI server mode: {sni_server_mode}")
print(f"REALITY SNI serverNames: {len(server_names)}")
print(f"Subscription REALITY nodes generated: {len(reality_nodes)}")
print(f"Subscription nodes generated: {len(nodes)}")
