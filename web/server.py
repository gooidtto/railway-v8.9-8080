import base64, os, secrets
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

SITE = Path(os.getenv("SITE_DIR", "/opt/web/site")).resolve()
TOKEN = os.getenv("SUB_TOKEN", "")
PORT = int(os.getenv("PORT", "8080"))

def vless_uri(name, uuid, host, port, public_key, sni, short_id, transport,
              encryption, path="/xhttp", mode="auto", flow=""):
    q = [
        ("encryption", encryption),
        ("security", "reality"),
        ("type", transport),
        ("fp", "chrome"),
        ("sni", sni),
        ("pbk", public_key),
        ("sid", short_id),
    ]
    if transport == "xhttp":
        q += [("path", path), ("mode", mode)]
    if flow:
        q += [("flow", flow)]
    query = "&".join(f"{k}={__import__('urllib.parse').parse.quote(str(v), safe='')}" for k,v in q)
    return f"vless://{uuid}@{host}:{int(port)}/?{query}#{name}"

def subscription():
    required = [
        "VISION_UUID","VISION_HOST","VISION_PORT","VISION_PUBLIC_KEY","VISION_SNI","VISION_SHORT_ID",
        "XHTTP_UUID","XHTTP_HOST","XHTTP_PORT","XHTTP_PUBLIC_KEY","XHTTP_SNI","XHTTP_SHORT_ID",
    ]
    missing = [x for x in required if not os.getenv(x)]
    if missing:
        raise RuntimeError("missing variables: " + ", ".join(missing))

    for key in ("VISION_ENCRYPTION", "XHTTP_ENCRYPTION"):
        if not os.getenv(key):
            raise RuntimeError(key + " is required")
    lines = [
        vless_uri(
            "VLESS-TCP-Vision-REALITY",
            os.environ["VISION_UUID"], os.environ["VISION_HOST"], os.environ["VISION_PORT"],
            os.environ["VISION_PUBLIC_KEY"], os.environ["VISION_SNI"], os.environ["VISION_SHORT_ID"],
            "tcp", os.environ["VISION_ENCRYPTION"], flow="xtls-rprx-vision"
        ),
        vless_uri(
            "VLESS-XHTTP-REALITY",
            os.environ["XHTTP_UUID"], os.environ["XHTTP_HOST"], os.environ["XHTTP_PORT"],
            os.environ["XHTTP_PUBLIC_KEY"], os.environ["XHTTP_SNI"], os.environ["XHTTP_SHORT_ID"],
            "xhttp", os.environ["XHTTP_ENCRYPTION"], path=os.getenv("XHTTP_PATH","/xhttp"), mode=os.getenv("XHTTP_MODE","auto")
        ),
    ]
    raw = "\n".join(lines) + "\n"
    return raw, base64.b64encode(raw.encode()).decode() + "\n"

class Handler(BaseHTTPRequestHandler):
    def send_bytes(self, status, ctype, body):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/health":
            self.send_bytes(200, "text/plain; charset=utf-8", b"OK\n")
            return
        if path.startswith("/sub/"):
            if not TOKEN or path != "/sub/" + TOKEN:
                self.send_bytes(404, "text/plain; charset=utf-8", b"Not Found\n")
                return
            try:
                raw, encoded = subscription()
                self.send_bytes(200, "text/plain; charset=utf-8", encoded.encode())
            except Exception as e:
                self.send_bytes(503, "text/plain; charset=utf-8", ("Subscription not ready: " + str(e) + "\n").encode())
            return
        rel = "index.html" if path == "/" else path.lstrip("/")
        target = (SITE / rel).resolve()
        if SITE not in target.parents and target != SITE or not target.is_file():
            self.send_bytes(404, "text/plain; charset=utf-8", b"Not Found\n")
            return
        types = {".html":"text/html; charset=utf-8",".js":"application/javascript; charset=utf-8",
                 ".css":"text/css; charset=utf-8",".json":"application/json; charset=utf-8"}
        self.send_bytes(200, types.get(target.suffix.lower(),"application/octet-stream"), target.read_bytes())

    def log_message(self, fmt, *args):
        return

if __name__ == "__main__":
    if not TOKEN:
        print("WARNING: SUB_TOKEN is not set; /sub/<token> will be unavailable", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
