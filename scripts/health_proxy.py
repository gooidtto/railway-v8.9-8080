import ipaddress
import json
import os
import select
import socket
import threading
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = int(os.getenv("PORT", "8080"))
UPSTREAM_HOST = "127.0.0.1"
UPSTREAM_PORT = int(os.getenv("XRAY_PORT", "10085"))
READY_FILE = os.getenv("XRAY_READY_FILE", "/data/.xray-ready")
SITE_DIR = Path(os.getenv("SITE_DIR", "/opt/xray/site")).resolve()
SUB_FILE = Path(os.getenv("SUBSCRIPTION_FILE", "/data/subscription.txt"))
SUB_TOKEN_FILE = Path(os.getenv("SUBSCRIPTION_TOKEN_FILE", "/data/subscription_token.txt"))
XHTTP_PATH = os.getenv("XHTTP_PATH", "/xhttp")

GEO_CACHE = {}
GEO_LOCK = threading.Lock()
GEO_TTL = int(os.getenv("GEO_CACHE_TTL", "600"))
GEO_TIMEOUT = float(os.getenv("GEO_TIMEOUT", "3"))
INFO_RATE_LIMIT = {}
INFO_RATE_LOCK = threading.Lock()
INFO_RATE_WINDOW = float(os.getenv("INFO_RATE_WINDOW", "5"))


def valid_ip(value):
    try:
        ip = ipaddress.ip_address(value.strip())
        if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_multicast:
            return None
        return ip
    except ValueError:
        return None


def client_ip_from_headers(headers, peer_ip):
    for item in headers.get("x-forwarded-for", "").split(","):
        ip = valid_ip(item)
        if ip:
            return str(ip)
    xreal = valid_ip(headers.get("x-real-ip", ""))
    return str(xreal) if xreal else str(peer_ip)


def geo_lookup(ip):
    if not ip:
        return {}
    now = time.time()
    with GEO_LOCK:
        cached = GEO_CACHE.get(ip)
        if cached and now - cached[0] < GEO_TTL:
            return cached[1]
    try:
        req = urllib.request.Request(
            f"https://ipapi.co/{ip}/json/",
            headers={"User-Agent": "railway-xray-network-info/1.0", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=GEO_TIMEOUT) as response:
            data = json.loads(response.read().decode("utf-8", "replace"))
        result = {
            "country": data.get("country_name") or "",
            "country_code": data.get("country_code") or "",
            "region": data.get("region") or "",
            "city": data.get("city") or "",
            "org": data.get("org") or "",
        }
    except Exception:
        result = {}
    with GEO_LOCK:
        GEO_CACHE[ip] = (now, result)
    return result


def resolver_ips():
    result = []
    try:
        for line in Path("/etc/resolv.conf").read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip().startswith("nameserver "):
                ip = line.split()[1]
                if ip not in result:
                    result.append(ip)
    except OSError:
        pass
    return result[:3]


def country_flag(code):
    code = (code or "").upper()
    if len(code) != 2 or not code.isalpha():
        return ""
    return "".join(chr(127397 + ord(c)) for c in code)


def network_info(headers, peer_ip):
    ip = client_ip_from_headers(headers, peer_ip)
    client_geo = geo_lookup(ip)
    resolvers = []
    for rip in resolver_ips():
        g = geo_lookup(rip) if valid_ip(rip) else {}
        resolvers.append({
            "ip": rip,
            "country": g.get("country", ""),
            "country_code": g.get("country_code", ""),
            "flag": country_flag(g.get("country_code", "")),
        })
    return {
        "ip": ip,
        "country": client_geo.get("country", ""),
        "country_code": client_geo.get("country_code", ""),
        "region": client_geo.get("region", ""),
        "city": client_geo.get("city", ""),
        "flag": country_flag(client_geo.get("country_code", "")),
        "edge": headers.get("x-railway-edge", ""),
        "deployment_region": os.getenv("RAILWAY_REPLICA_REGION", ""),
        "dns_resolvers": resolvers,
        "note": "DNS/route countries are estimates; browser DNS and BGP hops are not directly observable.",
    }


def http_response(status, content_type, body, head_only=False):
    if isinstance(body, str):
        body = body.encode("utf-8")
    reason = {200: "OK", 404: "Not Found", 405: "Method Not Allowed", 429: "Too Many Requests", 503: "Service Unavailable"}.get(status, "OK")
    head = (
        f"HTTP/1.1 {status} {reason}\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n"
        "Cache-Control: no-store\r\n"
        "X-Content-Type-Options: nosniff\r\n"
        "Referrer-Policy: no-referrer\r\n"
        "Permissions-Policy: camera=(), microphone=(), geolocation=()\r\n"
        "\r\n"
    ).encode()
    return head if head_only else head + body


def parse_http_request(data):
    try:
        head = data.split(b"\r\n\r\n", 1)[0]
        first = head.split(b"\r\n", 1)[0].decode("ascii", "strict")
        parts = first.split(" ", 2)
        if len(parts) != 3 or not parts[2].startswith("HTTP/"):
            return None
        method, target, _ = parts
        headers = {}
        for line in head.split(b"\r\n")[1:]:
            if b":" in line:
                key, value = line.split(b":", 1)
                try:
                    headers[key.decode("ascii").strip().lower()] = value.decode("latin-1").strip()
                except UnicodeDecodeError:
                    pass
        return method, urlsplit(target).path or "/", headers
    except (UnicodeDecodeError, ValueError):
        return None


def xray_ready():
    return os.path.exists(READY_FILE)


def relay(a, b):
    sockets = [a, b]
    while True:
        readable, _, exceptional = select.select(sockets, [], sockets, 300)
        if exceptional or not readable:
            return
        for src in readable:
            dst = b if src is a else a
            chunk = src.recv(65536)
            if not chunk:
                return
            dst.sendall(chunk)


def serve_static(client, path, head_only=False):
    rel = "index.html" if path == "/" else path.lstrip("/")
    target = (SITE_DIR / rel).resolve()
    if SITE_DIR not in target.parents and target != SITE_DIR or not target.is_file():
        client.sendall(http_response(404, "text/plain; charset=utf-8", "Not Found\n", head_only))
        return
    body = target.read_bytes()
    types = {
        ".html": "text/html; charset=utf-8",
        ".js": "application/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".svg": "image/svg+xml",
        ".ico": "image/x-icon",
    }
    client.sendall(http_response(200, types.get(target.suffix.lower(), "application/octet-stream"), body, head_only))


def subscription_token():
    try:
        return SUB_TOKEN_FILE.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return ""


def handle_subscription(client, method, path):
    token = subscription_token()
    if not token:
        client.sendall(http_response(503, "text/plain; charset=utf-8", "Subscription not ready\n", method == "HEAD"))
        return True
    prefix = "/sub/"
    if not path.startswith(prefix) or path != prefix + token:
        client.sendall(http_response(404, "text/plain; charset=utf-8", "Not Found\n", method == "HEAD"))
        return True
    if not SUB_FILE.is_file():
        client.sendall(http_response(503, "text/plain; charset=utf-8", "Subscription not ready\n", method == "HEAD"))
        return True
    client.sendall(http_response(200, "text/plain; charset=utf-8", SUB_FILE.read_bytes(), method == "HEAD"))
    return True


def handle_network_info(client, headers, peer_ip, head_only=False):
    now = time.time()
    key = peer_ip
    with INFO_RATE_LOCK:
        last = INFO_RATE_LIMIT.get(key, 0)
        if now - last < INFO_RATE_WINDOW:
            client.sendall(http_response(429, "application/json; charset=utf-8", '{"error":"rate_limited"}', head_only))
            return
        INFO_RATE_LIMIT[key] = now
    body = json.dumps(network_info(headers, peer_ip), ensure_ascii=False, separators=(",", ":"))
    client.sendall(http_response(200, "application/json; charset=utf-8", body, head_only))


def handle_http(client, method, path, headers, peer_ip):
    head_only = method == "HEAD"
    if method not in {"GET", "HEAD"}:
        client.sendall(http_response(405, "text/plain; charset=utf-8", "Method Not Allowed\n"))
        return True
    if path == "/api/network-info":
        handle_network_info(client, headers, peer_ip, head_only)
        return True
    if path == "/health":
        body = "OK\n" if xray_ready() else "NOT READY\n"
        status = 200 if xray_ready() else 503
        client.sendall(http_response(status, "text/plain; charset=utf-8", body, head_only))
        return True
    if path == "/sub" or path.startswith("/sub/"):
        return handle_subscription(client, method, path)
    if path == XHTTP_PATH or path.startswith(XHTTP_PATH + "/"):
        return False
    serve_static(client, path, head_only)
    return True


def peek_http_header(client, max_bytes=16384, timeout=5.0):
    deadline = time.monotonic() + timeout
    while True:
        remaining = max(0.05, deadline - time.monotonic())
        client.settimeout(remaining)
        try:
            buffered = client.recv(max_bytes, socket.MSG_PEEK)
        except socket.timeout:
            return b""
        if not buffered:
            return b""
        # Important: these are actual CRLF bytes, not the literal characters
        # backslash-r/backslash-n. A previous build used the latter and could
        # wait until timeout on every ordinary HTTP/XHTTP request.
        if b"\r\n\r\n" in buffered or b"\n\n" in buffered:
            return buffered
        if len(buffered) >= max_bytes:
            return buffered
        time.sleep(0.005)


def handle(client):
    client.settimeout(5)
    upstream = None
    try:
        buffered = peek_http_header(client)
        if not buffered:
            return
        parsed = parse_http_request(buffered)
        if parsed:
            method, path, headers = parsed
            result = handle_http(client, method, path, headers, client.getpeername()[0])
            if result is not False:
                return
        upstream = socket.create_connection((UPSTREAM_HOST, UPSTREAM_PORT), timeout=5)
        relay(client, upstream)
    except (OSError, TimeoutError):
        pass
    finally:
        if upstream is not None:
            try:
                upstream.close()
            except OSError:
                pass
        client.close()


def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((LISTEN_HOST, LISTEN_PORT))
        server.listen(256)
        print(f"public listener {LISTEN_HOST}:{LISTEN_PORT}; site=/; health=/health; sub=/sub; xhttp={XHTTP_PATH}; xray={UPSTREAM_HOST}:{UPSTREAM_PORT}", flush=True)
        while True:
            client, _ = server.accept()
            threading.Thread(target=handle, args=(client,), daemon=True).start()


if __name__ == "__main__":
    main()
