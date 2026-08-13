# H3 / HTTP/3 validation

## What is supported

Xray XHTTP/SplitHTTP supports QUIC/HTTP/3, but the transport used by a public endpoint must also carry UDP/QUIC. The current Railway TCP Proxy is a TCP ingress, so the Railway TCP Proxy endpoint must **not** be advertised as an H3 node.

The current deployment deliberately keeps:

- Railway public domain -> `8080`
- Railway TCP Proxy -> `8080`
- XHTTP -> `10086`
- REALITY/XHTTP -> `10087`

The runtime capability report therefore records:

- `h3_capable_in_xray = true`
- `h3_via_current_tcp_proxy = false`
- `h3_via_railway_https_edge = unknown-until-probed`

## Validation procedure

1. Deploy the development branch to a disposable Railway environment.
2. Keep the existing TCP Proxy on `8080`; do not use it for H3.
3. Test the public domain with a client that can explicitly report the negotiated HTTP version (for example a browser DevTools Network panel or a curl build with HTTP/3 support).
4. Record whether the public edge negotiates `h3` (QUIC) or `h2` (HTTP/2).
5. Independently test the TCP Proxy node. It must remain TCP/REALITY and must not be classified as H3.
6. Only add an H3-specific subscription node if the public endpoint demonstrably negotiates HTTP/3 and the client configuration can preserve that transport end-to-end.

## Acceptance criteria

A release may claim H3 support only when an external client reports an actual `h3`/QUIC negotiation. Xray's local capability alone is insufficient evidence because Railway's public edge and TCP Proxy determine the externally reachable transport.
