import socket
import sys

if len(sys.argv) != 3:
    raise SystemExit("usage: wait_port.py HOST PORT")

host = sys.argv[1]
port = int(sys.argv[2])
try:
    with socket.create_connection((host, port), timeout=1):
        pass
except OSError:
    raise SystemExit(1)
raise SystemExit(0)
