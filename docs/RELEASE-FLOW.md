# Release flow

## Branches

- `backup/v8.9-8080-stable-20260812`: immutable known-good baseline.
- `dev/v8.9-platform-hardening`: current integration/development branch.
- `main`: Railway production deployment source.

## Promotion gates

1. Code changes land on a development branch.
2. CI must pass Python compilation, gateway tests, subscription/material consistency tests, and platform capability tests.
3. Deploy the development commit to a disposable/test Railway environment when network behavior changes.
4. Verify the two currently supported nodes:
   - Railway HTTPS/XHTTP domain
   - Railway TCP Proxy -> `8080` -> REALITY/XHTTP
5. Verify the subscription still contains exactly two nodes unless a release explicitly changes that contract.
6. Verify the material manifest is generated and the ML-KEM/REALITY fingerprints remain stable across a restart with the same volume.
7. Only then fast-forward `main` to the validated development commit.
8. Create a new immutable backup tag/branch before the next risky change.

## Rollback

If a production deployment fails, move `main` back to the last validated stable commit. Never modify the stable backup branch in place.

## H3 gate

H3 is a separate promotion gate. Do not mark H3 as supported merely because Xray supports XHTTP/QUIC. The external Railway public edge must be observed negotiating HTTP/3 with a real client first. The TCP Proxy remains TCP and is never an H3 transport.
