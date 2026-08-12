#!/bin/sh
set -eu

DATA_DIR="${RAILWAY_VOLUME_MOUNT_PATH:-${DATA_DIR:-/data}}"
# Railway exposes the service on PORT. With the TCP Proxy configured to the
# same application port, one local TCP multiplexer must own PORT and dispatch
# HTTP to the web/subscription handler and TLS/REALITY to Xray.
GATEWAY_PORT="${PORT:-${PUBLIC_HTTP_PORT:-8080}}"
PORT="$GATEWAY_PORT"
XRAY_PORT="${XRAY_PORT:-10087}"
XRAY_HTTP_PORT="${XRAY_HTTP_PORT:-10086}"
XRAY_LISTEN="${XRAY_LISTEN:-127.0.0.1}"
CONFIG="${XRAY_CONFIG:-/etc/xray/config.json}"
REALITY_TARGET="${REALITY_TARGET:-www.cloudflare.com:443}"
REALITY_SNI="${REALITY_SNI:-${REALITY_TARGET%%:*}}"
REALITY_FINGERPRINT="${REALITY_FINGERPRINT:-chrome}"
XHTTP_PATH="${XHTTP_PATH:-/xhttp}"
XHTTP_MODE="${XHTTP_MODE:-auto}"
SHORT_ID="${SHORT_ID:-50175c035ee132}"
TCP_PROXY_PROTOCOL="${TCP_PROXY_PROTOCOL:-auto}"
RAILWAY_TCP_APPLICATION_PORT_VALUE="${RAILWAY_TCP_APPLICATION_PORT:-}"
SERVER_HOST="${SERVER_HOST:-${TCP_PROXY_HOST:-}}"
SERVER_PORT="${SERVER_PORT:-${TCP_PROXY_PORT:-}}"

# The public Railway TCP proxy must point to the gateway port (PORT), not the
# private Xray port. The gateway then forwards REALITY TLS to XRAY_PORT.
if [ -n "${XRAY_TCP_PROXY_HOST:-}" ] || [ -n "${XRAY_TCP_PROXY_PORT:-}" ]; then
  [ -n "${XRAY_TCP_PROXY_HOST:-}" ] && [ -n "${XRAY_TCP_PROXY_PORT:-}" ] || { echo "ERROR: XRAY_TCP_PROXY_HOST and XRAY_TCP_PROXY_PORT must be set together" >&2; exit 1; }
  SERVER_HOST="$XRAY_TCP_PROXY_HOST"
  SERVER_PORT="$XRAY_TCP_PROXY_PORT"
elif [ -z "$SERVER_HOST" ] && [ -z "$SERVER_PORT" ] && [ -n "${RAILWAY_TCP_PROXY_DOMAIN:-}" ] && [ -n "${RAILWAY_TCP_PROXY_PORT:-}" ]; then
  SERVER_HOST="$RAILWAY_TCP_PROXY_DOMAIN"
  SERVER_PORT="$RAILWAY_TCP_PROXY_PORT"
fi

READY_FILE="$DATA_DIR/.xray-ready"
SUB_TOKEN_FILE="$DATA_DIR/subscription_token.txt"
UUID_FILE="$DATA_DIR/uuid.txt"
PRIVATE_KEY_FILE="$DATA_DIR/reality_private_key.txt"
PUBLIC_KEY_FILE="$DATA_DIR/reality_public_key.txt"
VLESS_DECRYPTION_FILE="$DATA_DIR/vless_decryption.txt"
VLESS_ENCRYPTION_FILE="$DATA_DIR/vless_encryption.txt"
HEALTH_PID=""
XRAY_PID=""

case "$SHORT_ID" in ''|*[!0-9a-fA-F]*) echo "ERROR: SHORT_ID must be hexadecimal" >&2; exit 1;; esac
if [ $(( ${#SHORT_ID} % 2 )) -ne 0 ] || [ ${#SHORT_ID} -gt 16 ]; then echo "ERROR: SHORT_ID length invalid" >&2; exit 1; fi
case "$XHTTP_PATH" in /*) ;; *) echo "ERROR: XHTTP_PATH must start with /" >&2; exit 1;; esac
mkdir -p "$DATA_DIR" "$(dirname "$CONFIG")"
chmod 0700 "$DATA_DIR" 2>/dev/null || true
rm -f "$READY_FILE"

if [ -s "$UUID_FILE" ]; then
  UUID=$(tr -d '[:space:]' < "$UUID_FILE")
else
  UUID=$(xray uuid)
  [ -n "$UUID" ] || { echo "ERROR: xray uuid returned empty output" >&2; exit 1; }
  printf '%s\n' "$UUID" > "$UUID_FILE"
fi

if [ -s "$PRIVATE_KEY_FILE" ] && [ -s "$PUBLIC_KEY_FILE" ]; then
  PRIVATE_KEY=$(tr -d '[:space:]' < "$PRIVATE_KEY_FILE")
  PUBLIC_KEY=$(tr -d '[:space:]' < "$PUBLIC_KEY_FILE")
else
  KEY_OUTPUT=$(xray x25519 2>&1) || { echo "$KEY_OUTPUT" >&2; exit 1; }
  PRIVATE_KEY=$(printf '%s\n' "$KEY_OUTPUT" | awk '/^PrivateKey[[:space:]]*:/ {sub(/^[^:]*:[[:space:]]*/,""); print; exit} /^Private[[:space:]]+key[[:space:]]*:/ {sub(/^[^:]*:[[:space:]]*/,""); print; exit}')
  PUBLIC_KEY=$(printf '%s\n' "$KEY_OUTPUT" | awk '/^Password([[:space:]]*\([^)]*\))?[[:space:]]*:/ {sub(/^[^:]*:[[:space:]]*/,""); print; exit} /^Public[[:space:]]+key[[:space:]]*:/ {sub(/^[^:]*:[[:space:]]*/,""); print; exit}')
  [ -n "$PRIVATE_KEY" ] && [ -n "$PUBLIC_KEY" ] || { echo "ERROR: unable to parse x25519 output" >&2; exit 1; }
  printf '%s\n' "$PRIVATE_KEY" > "$PRIVATE_KEY_FILE"
  printf '%s\n' "$PUBLIC_KEY" > "$PUBLIC_KEY_FILE"
fi
chmod 0600 "$UUID_FILE" "$PRIVATE_KEY_FILE" "$PUBLIC_KEY_FILE" 2>/dev/null || true

if [ -s "$VLESS_DECRYPTION_FILE" ] && [ -s "$VLESS_ENCRYPTION_FILE" ]; then
  VLESS_DECRYPTION=$(tr -d '[:space:]' < "$VLESS_DECRYPTION_FILE")
  VLESS_ENCRYPTION=$(tr -d '[:space:]' < "$VLESS_ENCRYPTION_FILE")
else
  TMP="$DATA_DIR/.vlessenc-output.tmp"
  umask 077
  xray vlessenc > "$TMP" 2>&1 || { cat "$TMP" >&2; rm -f "$TMP"; exit 1; }
  VLESS_DECRYPTION=$(awk '/Authentication:[[:space:]]*ML-KEM-768,[[:space:]]*Post-Quantum/ {m=1;next} m && /"decryption"[[:space:]]*:/ {line=$0;sub(/^.*"decryption"[[:space:]]*:[[:space:]]*"/,"",line);sub(/".*$/,"",line);print line;exit}' "$TMP")
  VLESS_ENCRYPTION=$(awk '/Authentication:[[:space:]]*ML-KEM-768,[[:space:]]*Post-Quantum/ {m=1;next} m && /"encryption"[[:space:]]*:/ {line=$0;sub(/^.*"encryption"[[:space:]]*:[[:space:]]*"/,"",line);sub(/".*$/,"",line);print line;exit}' "$TMP")
  rm -f "$TMP"
  [ -n "$VLESS_DECRYPTION" ] && [ -n "$VLESS_ENCRYPTION" ] || { echo "ERROR: unable to parse ML-KEM-768 VLESS Encryption output" >&2; exit 1; }
  printf '%s\n' "$VLESS_DECRYPTION" > "$VLESS_DECRYPTION_FILE"
  printf '%s\n' "$VLESS_ENCRYPTION" > "$VLESS_ENCRYPTION_FILE"
  chmod 0600 "$VLESS_DECRYPTION_FILE" "$VLESS_ENCRYPTION_FILE"
fi

if [ -s "$SUB_TOKEN_FILE" ]; then
  SUBSCRIPTION_TOKEN=$(tr -d '[:space:]' < "$SUB_TOKEN_FILE")
else
  SUBSCRIPTION_TOKEN=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
  printf '%s\n' "$SUBSCRIPTION_TOKEN" > "$SUB_TOKEN_FILE"
fi
case "$SUBSCRIPTION_TOKEN" in *[!A-Za-z0-9_-]*|'') echo "ERROR: invalid subscription token" >&2; exit 1;; esac
chmod 0600 "$SUB_TOKEN_FILE"

# generate.py uses SERVER_HOST/SERVER_PORT as the public TCP endpoint, while
# XRAY_PORT is now private. This allows Railway TCP :50192 -> application PORT
# and the same application PORT to serve the public HTTPS/subscription path.
export PORT PUBLIC_HTTP_PORT="$GATEWAY_PORT" GATEWAY_PORT DATA_DIR XRAY_PORT XRAY_HTTP_PORT XRAY_LISTEN CONFIG REALITY_TARGET REALITY_SNI REALITY_FINGERPRINT XHTTP_PATH XHTTP_MODE SHORT_ID UUID PRIVATE_KEY PUBLIC_KEY VLESS_DECRYPTION VLESS_ENCRYPTION SERVER_HOST SERVER_PORT SUBSCRIPTION_TOKEN TCP_PROXY_PROTOCOL XRAY_READY_FILE="$READY_FILE"

python3 /opt/xray/scripts/health_proxy.py & HEALTH_PID=$!
cleanup(){
  rm -f "$READY_FILE"
  [ -n "$XRAY_PID" ] && kill "$XRAY_PID" 2>/dev/null || true
  [ -n "$HEALTH_PID" ] && kill "$HEALTH_PID" 2>/dev/null || true
  [ -n "$XRAY_PID" ] && wait "$XRAY_PID" 2>/dev/null || true
  [ -n "$HEALTH_PID" ] && wait "$HEALTH_PID" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

echo "Railway PORT/gateway: $GATEWAY_PORT; private Xray REALITY: $XRAY_PORT; XHTTP: $XRAY_HTTP_PORT" >&2
echo "TCP subscription endpoint: ${SERVER_HOST:-disabled}:${SERVER_PORT:-}" >&2
echo "Railway TCP application port: ${RAILWAY_TCP_APPLICATION_PORT_VALUE:-unset}" >&2
python3 /opt/xray/scripts/generate.py --no-subscription

xray run -test -config "$CONFIG"
echo "Starting Xray on ${XRAY_LISTEN}:$XRAY_PORT; gateway listens on 0.0.0.0:$GATEWAY_PORT" >&2
xray run -config "$CONFIG" & XRAY_PID=$!
READY=0
for _ in $(seq 1 60); do
  if python3 /opt/xray/scripts/wait_port.py 127.0.0.1 "$XRAY_PORT"; then READY=1; break; fi
  if ! kill -0 "$XRAY_PID" 2>/dev/null; then echo "ERROR: Xray exited before becoming ready" >&2; wait "$XRAY_PID" || true; exit 1; fi
  sleep 1
done
[ "$READY" -eq 1 ] || { echo "ERROR: Xray did not become ready within 60 seconds" >&2; exit 1; }
touch "$READY_FILE"

PUBLIC_DOMAIN="${RAILWAY_PUBLIC_DOMAIN:-}"
if [ -n "$PUBLIC_DOMAIN" ]; then
  printf 'https://%s/sub/%s\n' "$PUBLIC_DOMAIN" "$SUBSCRIPTION_TOKEN" > "$DATA_DIR/subscription_url.txt"
  chmod 0600 "$DATA_DIR/subscription_url.txt"
fi
echo "Website: ${PUBLIC_DOMAIN:+https://$PUBLIC_DOMAIN/}" >&2
echo "Xray ready; gateway=$GATEWAY_PORT reality=$XRAY_PORT xhttp=$XRAY_HTTP_PORT" >&2
wait "$XRAY_PID"
