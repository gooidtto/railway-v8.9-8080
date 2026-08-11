# Web Subscription Service

This service publishes one protected subscription containing both nodes:

1. VLESS + TCP + XTLS Vision + REALITY
2. VLESS + XHTTP + REALITY

Set the Railway TCP Proxy host/port and REALITY public parameters from the two Xray services.

Required variables:
- SUB_TOKEN
- VISION_ENCRYPTION / XHTTP_ENCRYPTION
- VISION_UUID / VISION_HOST / VISION_PORT / VISION_PUBLIC_KEY / VISION_SNI / VISION_SHORT_ID
- XHTTP_UUID / XHTTP_HOST / XHTTP_PORT / XHTTP_PUBLIC_KEY / XHTTP_SNI / XHTTP_SHORT_ID
- XHTTP_PATH (default `/xhttp`)
- XHTTP_MODE (default `auto`)
