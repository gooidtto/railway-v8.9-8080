#!/bin/sh
set -eu

DATA_DIR="${RAILWAY_VOLUME_MOUNT_PATH:-${DATA_DIR:-/data}}"
XRAY_PORT="${PORT:-8080}"
CONFIG="${XRAY_CONFIG:-/etc/xray/config.json}"

mkdir -p "$DATA_DIR" "$(dirname "$CONFIG")"
chmod 0700 "$DATA_DIR" 2>/dev/null || true

UUID_FILE="$DATA_DIR/uuid.txt"
PRIVATE_FILE="$DATA_DIR/reality_private_key.txt"
PUBLIC_FILE="$DATA_DIR/reality_public_key.txt"
DEC_FILE="$DATA_DIR/vless_decryption.txt"
ENC_FILE="$DATA_DIR/vless_encryption.txt"

if [ -s "$UUID_FILE" ]; then
  UUID=$(tr -d '[:space:]' < "$UUID_FILE")
else
  UUID=$(xray uuid)
  printf '%s\n' "$UUID" > "$UUID_FILE"
fi

if [ -s "$PRIVATE_FILE" ] && [ -s "$PUBLIC_FILE" ]; then
  PRIVATE_KEY=$(tr -d '[:space:]' < "$PRIVATE_FILE")
  PUBLIC_KEY=$(tr -d '[:space:]' < "$PUBLIC_FILE")
else
  OUT=$(xray x25519 2>&1)
  PRIVATE_KEY=$(printf '%s\n' "$OUT" | awk -F': ' '/^PrivateKey:/ {print $2; exit}')
  # Current Xray names the REALITY public key "Password".
  PUBLIC_KEY=$(printf '%s\n' "$OUT" | awk -F': ' '/^Password:/ {print $2; exit}')
  [ -n "$PRIVATE_KEY" ] && [ -n "$PUBLIC_KEY" ] || {
    echo "ERROR: xray x25519 key generation failed" >&2
    printf '%s\n' "$OUT" >&2
    exit 1
  }
  printf '%s\n' "$PRIVATE_KEY" > "$PRIVATE_FILE"
  printf '%s\n' "$PUBLIC_KEY" > "$PUBLIC_FILE"
fi
chmod 0600 "$UUID_FILE" "$PRIVATE_FILE" "$PUBLIC_FILE"

if [ -s "$DEC_FILE" ] && [ -s "$ENC_FILE" ]; then
  VLESS_DECRYPTION=$(tr -d '[:space:]' < "$DEC_FILE")
  VLESS_ENCRYPTION=$(tr -d '[:space:]' < "$ENC_FILE")
else
  TMP="$DATA_DIR/.vlessenc.tmp"
  xray vlessenc > "$TMP" 2>&1 || {
    cat "$TMP" >&2
    rm -f "$TMP"
    exit 1
  }
  VLESS_DECRYPTION=$(awk '
    /Authentication: ML-KEM-768/ {f=1;next}
    f && /"decryption"/ {
      sub(/^.*"decryption"[[:space:]]*:[[:space:]]*"/,"")
      sub(/".*$/,"")
      print
      exit
    }' "$TMP")
  VLESS_ENCRYPTION=$(awk '
    /Authentication: ML-KEM-768/ {f=1;next}
    f && /"encryption"/ {
      sub(/^.*"encryption"[[:space:]]*:[[:space:]]*"/,"")
      sub(/".*$/,"")
      print
      exit
    }' "$TMP")
  rm -f "$TMP"
  [ -n "$VLESS_DECRYPTION" ] && [ -n "$VLESS_ENCRYPTION" ] || {
    echo "ERROR: unable to parse ML-KEM-768 VLESS encryption values" >&2
    exit 1
  }
  printf '%s\n' "$VLESS_DECRYPTION" > "$DEC_FILE"
  printf '%s\n' "$VLESS_ENCRYPTION" > "$ENC_FILE"
fi
chmod 0600 "$DEC_FILE" "$ENC_FILE"

export DATA_DIR XRAY_PORT XRAY_CONFIG UUID PRIVATE_KEY PUBLIC_KEY VLESS_DECRYPTION
python3 /opt/xray/generate.py

# Fail deployment immediately if the generated Xray config is invalid.
xray run -test -config "$CONFIG"

echo "========================================"
echo "Xray protocol : $PROTOCOL"
echo "Xray listen   : 0.0.0.0:$XRAY_PORT"
echo "UUID          : $UUID"
echo "REALITY pubkey: $PUBLIC_KEY"
echo "REALITY SNI   : ${REALITY_SNI:-}"
echo "REALITY SID   : ${SHORT_ID:-}"
echo "VLESS enc     : $VLESS_ENCRYPTION"
echo "Railway TCP target: $XRAY_PORT"
echo "========================================"

exec xray run -config "$CONFIG"
