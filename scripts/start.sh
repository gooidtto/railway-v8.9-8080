#!/bin/sh
set -eu

DATA_DIR="${RAILWAY_VOLUME_MOUNT_PATH:-${DATA_DIR:-/data}}"
PORT="${PORT:-8080}"
XRAY_PORT="${XRAY_PORT:-10085}"
XRAY_LISTEN="${XRAY_LISTEN:-0.0.0.0}"
CONFIG="${XRAY_CONFIG:-/etc/xray/config.json}"
REALITY_TARGET="${REALITY_TARGET:-www.cloudflare.com:443}"
REALITY_SNI="${REALITY_SNI:-${REALITY_TARGET%%:*}}"
REALITY_FINGERPRINT="${REALITY_FINGERPRINT:-chrome}"
XHTTP_PATH="${XHTTP_PATH:-/xhttp}"
XHTTP_MODE="${XHTTP_MODE:-auto}"
SHORT_ID="${SHORT_ID:-50175c035ee132}"
# Explicit values take precedence. Railway's singular TCP proxy variables are
# ambiguous when more than one TCP proxy exists on the same service.
SERVER_HOST="${SERVER_HOST:-${TCP_PROXY_HOST:-}}"
SERVER_PORT="${SERVER_PORT:-${TCP_PROXY_PORT:-}}"
RAILWAY_TCP_APPLICATION_PORT_VALUE="${RAILWAY_TCP_APPLICATION_PORT:-}"
if [ -z "$SERVER_HOST" ] && [ -z "$SERVER_PORT" ]; then
  SERVER_HOST="${RAILWAY_TCP_PROXY_DOMAIN:-}"
  SERVER_PORT="${RAILWAY_TCP_PROXY_PORT:-}"
fi
READY_FILE="$DATA_DIR/.xray-ready"
SUB_TOKEN_FILE="$DATA_DIR/subscription_token.txt"
HEALTH_PID=""
XRAY_PID=""

case "$XHTTP_PATH" in /*) ;; *) echo "ERROR: XHTTP_PATH must start with /" >&2; exit 1;; esac
case "$SHORT_ID" in ''|*[!0-9a-fA-F]*) echo "ERROR: SHORT_ID must be hexadecimal" >&2; exit 1;; esac
if [ $(( ${#SHORT_ID} % 2 )) -ne 0 ] || [ ${#SHORT_ID} -gt 16 ]; then
  echo "ERROR: SHORT_ID must contain 0-16 hexadecimal characters with even length" >&2
  exit 1
fi
if [ "$XRAY_PORT" = "$PORT" ]; then
  echo "ERROR: XRAY_PORT must differ from public PORT" >&2
  exit 1
fi
# A service may have multiple Railway TCP proxies, but Railway exposes only
# one singular RAILWAY_TCP_PROXY_* pair to the process. Never silently publish
# a subscription for a proxy targeting the HTTP port.
if [ -n "$RAILWAY_TCP_APPLICATION_PORT_VALUE" ] && [ "$RAILWAY_TCP_APPLICATION_PORT_VALUE" != "$XRAY_PORT" ] && [ -z "${TCP_PROXY_HOST:-}" ] && [ -z "${TCP_PROXY_PORT:-}" ] && [ -z "${SERVER_HOST:-}" ] && [ -z "${SERVER_PORT:-}" ]; then
  echo "ERROR: Railway TCP proxy target is ${RAILWAY_TCP_APPLICATION_PORT_VALUE}, but Xray listens on ${XRAY_PORT}. Remove the stale TCP proxy or set TCP_PROXY_HOST/TCP_PROXY_PORT to the proxy targeting ${XRAY_PORT}." >&2
  exit 1
fi
if [ -z "$SERVER_HOST" ] || [ -z "$SERVER_PORT" ]; then
  echo "ERROR: no TCP proxy endpoint is available for subscription generation" >&2
  exit 1
fi

mkdir -p "$DATA_DIR" "$(dirname "$CONFIG")"
chmod 0700 "$DATA_DIR" 2>/dev/null || true
rm -f "$READY_FILE"

UUID_FILE="$DATA_DIR/uuid.txt"
PRIVATE_KEY_FILE="$DATA_DIR/reality_private_key.txt"
PUBLIC_KEY_FILE="$DATA_DIR/reality_public_key.txt"
VLESS_DECRYPTION_FILE="$DATA_DIR/vless_decryption.txt"
VLESS_ENCRYPTION_FILE="$DATA_DIR/vless_encryption.txt"

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
  KEY_OUTPUT=""
  KEY_STATUS=0
  if KEY_OUTPUT=$(xray x25519 2>&1); then KEY_STATUS=0; else KEY_STATUS=$?; fi
  PRIVATE_KEY=$(printf '%s\n' "$KEY_OUTPUT" | awk '{gsub(/\r/,""); sub(/^[[:space:]]+/,"")} $0 ~ /^PrivateKey[[:space:]]*:/ {sub(/^[^:]*:[[:space:]]*/,""); print; exit} $0 ~ /^Private[[:space:]]+key[[:space:]]*:/ {sub(/^[^:]*:[[:space:]]*/,""); print; exit}')
  PUBLIC_KEY=$(printf '%s\n' "$KEY_OUTPUT" | awk '{gsub(/\r/,""); sub(/^[[:space:]]+/,"")} $0 ~ /^Password([[:space:]]*\([^)]*\))?[[:space:]]*:/ {sub(/^[^:]*:[[:space:]]*/,""); print; exit} $0 ~ /^Public[[:space:]]+key[[:space:]]*:/ {sub(/^[^:]*:[[:space:]]*/,""); print; exit}')
  if [ -z "$PRIVATE_KEY" ] || [ -z "$PUBLIC_KEY" ]; then
    echo "ERROR: unable to parse x25519 key output" >&2
    echo "ERROR: xray x25519 exit status: $KEY_STATUS" >&2
    exit 1
  fi
  case "$PRIVATE_KEY" in *[!A-Za-z0-9_-]*|'') echo "ERROR: parsed PrivateKey is invalid" >&2; exit 1;; esac
  case "$PUBLIC_KEY" in *[!A-Za-z0-9_-]*|'') echo "ERROR: parsed public key is invalid" >&2; exit 1;; esac
  printf '%s\n' "$PRIVATE_KEY" > "$PRIVATE_KEY_FILE"
  printf '%s\n' "$PUBLIC_KEY" > "$PUBLIC_KEY_FILE"
fi
chmod 0600 "$UUID_FILE" "$PRIVATE_KEY_FILE" "$PUBLIC_KEY_FILE" 2>/dev/null || true

if [ -s "$VLESS_DECRYPTION_FILE" ] && [ -s "$VLESS_ENCRYPTION_FILE" ]; then
  VLESS_DECRYPTION=$(tr -d '[:space:]' < "$VLESS_DECRYPTION_FILE")
  VLESS_ENCRYPTION=$(tr -d '[:space:]' < "$VLESS_ENCRYPTION_FILE")
else
  VLESSENC_OUTPUT_FILE="$DATA_DIR/.vlessenc-output.tmp"
  umask 077
  if ! xray vlessenc > "$VLESSENC_OUTPUT_FILE" 2>&1; then
    echo "ERROR: xray vlessenc failed" >&2
    rm -f "$VLESSENC_OUTPUT_FILE"
    exit 1
  fi
  VLESS_DECRYPTION=$(awk '/Authentication:[[:space:]]*ML-KEM-768,[[:space:]]*Post-Quantum/ { mlkem=1; next } mlkem && /"decryption"[[:space:]]*:/ { line=$0; sub(/^.*"decryption"[[:space:]]*:[[:space:]]*"/, "", line); sub(/".*$/, "", line); print line; exit }' "$VLESSENC_OUTPUT_FILE")
  VLESS_ENCRYPTION=$(awk '/Authentication:[[:space:]]*ML-KEM-768,[[:space:]]*Post-Quantum/ { mlkem=1; next } mlkem && /"encryption"[[:space:]]*:/ { line=$0; sub(/^.*"encryption"[[:space:]]*:[[:space:]]*"/, "", line); sub(/".*$/, "", line); print line; exit }' "$VLESSENC_OUTPUT_FILE")
  rm -f "$VLESSENC_OUTPUT_FILE"
  if [ -z "$VLESS_DECRYPTION" ] || [ -z "$VLESS_ENCRYPTION" ]; then
    echo "ERROR: unable to parse ML-KEM-768 VLESS Encryption output" >&2
    exit 1
  fi
  case "$VLESS_DECRYPTION" in *[!A-Za-z0-9._-]*|'') echo "ERROR: invalid VLESS decryption value" >&2; exit 1;; esac
  case "$VLESS_ENCRYPTION" in *[!A-Za-z0-9._-]*|'') echo "ERROR: invalid VLESS encryption value" >&2; exit 1;; esac
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

export DATA_DIR PORT XRAY_PORT XRAY_LISTEN CONFIG REALITY_TARGET REALITY_SNI REALITY_FINGERPRINT XHTTP_PATH XHTTP_MODE SHORT_ID UUID PRIVATE_KEY PUBLIC_KEY VLESS_DECRYPTION VLESS_ENCRYPTION SERVER_HOST SERVER_PORT SUBSCRIPTION_TOKEN XRAY_READY_FILE="$READY_FILE"

python3 /opt/xray/scripts/health_proxy.py & HEALTH_PID=$!
cleanup(){
  rm -f "$READY_FILE"
  [ -z "$XRAY_PID" ] || kill "$XRAY_PID" 2>/dev/null || true
  [ -z "$HEALTH_PID" ] || kill "$HEALTH_PID" 2>/dev/null || true
  [ -z "$XRAY_PID" ] || wait "$XRAY_PID" 2>/dev/null || true
  [ -z "$HEALTH_PID" ] || wait "$HEALTH_PID" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

echo "TCP subscription endpoint: ${SERVER_HOST}:${SERVER_PORT}" >&2
echo "Railway TCP application port reported: ${RAILWAY_TCP_APPLICATION_PORT_VALUE:-unset}; Xray port: ${XRAY_PORT}" >&2

echo "VLESS Encryption: ML-KEM-768 (Post-Quantum) enabled" >&2
echo "REALITY target: $REALITY_TARGET" >&2
python3 /opt/xray/scripts/generate.py

xray run -test -config "$CONFIG"
echo "Starting Xray on ${XRAY_LISTEN}:$XRAY_PORT; public HTTP listener is 0.0.0.0:$PORT" >&2
xray run -config "$CONFIG" & XRAY_PID=$!
READY=0
for _ in $(seq 1 60); do
  if python3 /opt/xray/scripts/wait_port.py 127.0.0.1 "$XRAY_PORT"; then READY=1; break; fi
  if ! kill -0 "$XRAY_PID" 2>/dev/null; then
    echo "ERROR: Xray exited before becoming ready" >&2
    wait "$XRAY_PID" || true
    exit 1
  fi
  sleep 1
done
if [ "$READY" -ne 1 ]; then
  echo "ERROR: Xray did not become ready within 60 seconds" >&2
  exit 1
fi
touch "$READY_FILE"

PUBLIC_DOMAIN="${RAILWAY_PUBLIC_DOMAIN:-}"
if [ -n "$PUBLIC_DOMAIN" ]; then
  printf 'https://%s/sub/%s\n' "$PUBLIC_DOMAIN" "$SUBSCRIPTION_TOKEN" > "$DATA_DIR/subscription_url.txt"
  chmod 0600 "$DATA_DIR/subscription_url.txt"
  echo "Subscription URL saved to /data/subscription_url.txt (token redacted from logs)" >&2
fi
echo "Website: ${PUBLIC_DOMAIN:+https://$PUBLIC_DOMAIN/}" >&2
echo "Xray ready; HTTP port=$PORT; Xray TCP port=$XRAY_PORT listen=$XRAY_LISTEN" >&2
wait "$XRAY_PID"
