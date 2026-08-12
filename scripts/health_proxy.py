import os
import select
import socket
import threading
from pathlib import Path
from urllib.parse import urlsplit

LISTEN_HOST="0.0.0.0"; LISTEN_PORT=int(os.getenv("PORT","8080"))
REALITY_HOST="127.0.0.1"; REALITY_PORT=int(os.getenv("XRAY_PORT","10085"))
HTTP_XHTTP_HOST="127.0.0.1"; HTTP_XHTTP_PORT=int(os.getenv("XRAY_HTTP_PORT","10086"))
READY_FILE=os.getenv("XRAY_READY_FILE","/data/.xray-ready")
SITE_DIR=Path(os.getenv("SITE_DIR","/opt/xray/site")).resolve()
SUB_FILE=Path(os.getenv("SUBSCRIPTION_FILE","/data/subscription.txt"))
SUB_TOKEN_FILE=Path(os.getenv("SUBSCRIPTION_TOKEN_FILE","/data/subscription_token.txt"))
XHTTP_PATH=os.getenv("XHTTP_PATH","/xhttp")


def log(m): print(f"[tcp-proxy] {m}",flush=True)
def ready(): return Path(READY_FILE).exists()
def tune(s):
    for level,opt,val in ((socket.IPPROTO_TCP,socket.TCP_NODELAY,1),(socket.SOL_SOCKET,socket.SO_KEEPALIVE,1)):
        try:s.setsockopt(level,opt,val)
        except OSError:pass

def response(status,ctype,body,head=False):
    if isinstance(body,str): body=body.encode()
    reason={200:"OK",404:"Not Found",405:"Method Not Allowed",503:"Service Unavailable"}.get(status,"OK")
    h=(f"HTTP/1.1 {status} {reason}\r\nContent-Type: {ctype}\r\nContent-Length: {len(body)}\r\nConnection: close\r\nCache-Control: no-store\r\nX-Content-Type-Options: nosniff\r\n\r\n").encode()
    return h if head else h+body

def parse_http(data):
    try:
        head=data.split(b"\r\n\r\n",1)[0]; first=head.split(b"\r\n",1)[0].decode("ascii")
        p=first.split(" ",2)
        if len(p)!=3 or not p[2].startswith("HTTP/"): return None
        return p[0],urlsplit(p[1]).path or "/"
    except (UnicodeDecodeError,ValueError): return None

def is_tls(data): return len(data)>=3 and data[0]==0x16 and data[1]==0x03 and data[2] in (1,2,3,4)

def recv_initial(s,timeout=10):
    s.settimeout(timeout); data=bytearray(); methods=(b"GET ",b"HEAD ",b"POST ",b"PUT ",b"DELETE ",b"OPTIONS ",b"PATCH ",b"CONNECT ")
    while len(data)<16384:
        c=s.recv(min(4096,16384-len(data)))
        if not c: break
        data.extend(c); raw=bytes(data)
        if is_tls(raw): return raw,"tls"
        if b"\r\n\r\n" in raw or b"\n\n" in raw: return raw,"http"
        if len(raw)>=3 and not raw.startswith(methods): return raw,"tcp"
    return bytes(data),("empty" if not data else "http")

def relay(a,b,initial=b""):
    tune(a);tune(b);a.settimeout(None);b.settimeout(None)
    if initial:b.sendall(initial)
    c2s,s2c=len(initial),0
    while True:
        readable,_,bad=select.select((a,b),(),(a,b),300)
        if bad or not readable:return c2s,s2c
        for src in readable:
            dst=b if src is a else a; chunk=src.recv(65536)
            if not chunk:return c2s,s2c
            dst.sendall(chunk)
            if src is a:c2s+=len(chunk)
            else:s2c+=len(chunk)

def connect(host,port):
    s=socket.create_connection((host,port),timeout=10);tune(s);return s

def token():
    try:return SUB_TOKEN_FILE.read_text().strip()
    except OSError:return ""

def handle_http(c,method,path):
    # XHTTP is an HTTP transport and may use POST/GET. It must be routed before
    # the website's GET/HEAD method restriction.
    if path==XHTTP_PATH or path.startswith(XHTTP_PATH+"/"): return False
    if method not in {"GET","HEAD"}:
        c.sendall(response(405,"text/plain; charset=utf-8","Method Not Allowed\n"));return True
    head=method=="HEAD"
    if path=="/health":
        ok=ready();c.sendall(response(200 if ok else 503,"text/plain; charset=utf-8","OK\n" if ok else "NOT READY\n",head));return True
    if path.startswith("/sub/"):
        t=token()
        if not t or path!="/sub/"+t or not SUB_FILE.is_file(): c.sendall(response(404,"text/plain; charset=utf-8","Not Found\n",head))
        else:c.sendall(response(200,"text/plain; charset=utf-8",SUB_FILE.read_bytes(),head))
        return True
    if path=="/sub":
        c.sendall(response(404,"text/plain; charset=utf-8","Not Found\n",head));return True
    rel="index.html" if path=="/" else path.lstrip("/");target=(SITE_DIR/rel).resolve()
    if SITE_DIR not in target.parents and target!=SITE_DIR or not target.is_file():
        c.sendall(response(404,"text/plain; charset=utf-8","Not Found\n",head));return True
    body=target.read_bytes();types={".html":"text/html; charset=utf-8",".css":"text/css; charset=utf-8",".js":"application/javascript; charset=utf-8",".json":"application/json; charset=utf-8",".svg":"image/svg+xml",".png":"image/png",".jpg":"image/jpeg",".jpeg":"image/jpeg"}
    c.sendall(response(200,types.get(target.suffix.lower(),"application/octet-stream"),body,head));return True

def handle(c):
    peer="unknown";up=None
    try:p=c.getpeername();peer=f"{p[0]}:{p[1]}"
    except OSError:pass
    tune(c);log(f"ACCEPT peer={peer} reality={REALITY_HOST}:{REALITY_PORT} http_xhttp={HTTP_XHTTP_HOST}:{HTTP_XHTTP_PORT} ready={ready()}")
    try:
        initial,kind=recv_initial(c)
        if not initial:log(f"CLOSE peer={peer} reason=no-initial-data");return
        log(f"CLASSIFY peer={peer} kind={kind} bytes={len(initial)} head={initial[:12].hex()}")
        if kind=="tls":
            up=connect(REALITY_HOST,REALITY_PORT);log(f"UPSTREAM_CONNECTED peer={peer} target={REALITY_HOST}:{REALITY_PORT} kind=tls-reality");a,b=relay(c,up,initial);log(f"RELAY_END peer={peer} kind=tls-reality c2s={a} s2c={b}");return
        parsed=parse_http(initial)
        if parsed:
            method,path=parsed;log(f"HTTP peer={peer} method={method} path={path}")
            if handle_http(c,method,path):log(f"HTTP_END peer={peer} path={path}");return
            kind="http-xhttp"
        target=(HTTP_XHTTP_HOST,HTTP_XHTTP_PORT) if kind=="http-xhttp" else (REALITY_HOST,REALITY_PORT)
        up=connect(*target);log(f"UPSTREAM_CONNECTED peer={peer} target={target[0]}:{target[1]} kind={kind}");a,b=relay(c,up,initial);log(f"RELAY_END peer={peer} kind={kind} c2s={a} s2c={b}")
    except (OSError,TimeoutError) as e:log(f"ERROR peer={peer} type={type(e).__name__} detail={e}")
    finally:
        if up:
            try:up.close()
            except OSError:pass
        try:c.close()
        except OSError:pass
        log(f"CLOSE peer={peer}")

def main():
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind((LISTEN_HOST,LISTEN_PORT));s.listen(256)
        log(f"LISTEN {LISTEN_HOST}:{LISTEN_PORT} reality={REALITY_HOST}:{REALITY_PORT} http_xhttp={HTTP_XHTTP_HOST}:{HTTP_XHTTP_PORT} xhttp={XHTTP_PATH}")
        while True:
            c,_=s.accept();threading.Thread(target=handle,args=(c,),daemon=True).start()

if __name__=="__main__":main()
