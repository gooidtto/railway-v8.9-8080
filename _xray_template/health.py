import os, socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.getenv("PORT","8080"))
READY = os.getenv("READY_FILE","/data/.xray-ready")

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/health":
            self.send_response(404); self.end_headers(); return
        ok = os.path.exists(READY)
        self.send_response(200 if ok else 503)
        self.send_header("Content-Type","text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write((b"OK\n" if ok else b"NOT READY\n"))
    def log_message(self,*a): return

ThreadingHTTPServer(("0.0.0.0",PORT),H).serve_forever()
