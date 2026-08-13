# syntax=docker/dockerfile:1
ARG XRAY_VERSION=26.3.27
ARG V89_BUILD_REVISION=v8.9-sni-matrix-r06-20260813
FROM ghcr.io/xtls/xray-core:${XRAY_VERSION}@sha256:592ec4d11f656db95598d01e76dbcc6e002d67360b96a5436500a938230f52c7 AS xray
FROM python:3.12-alpine3.22
ARG XRAY_VERSION
ARG V89_BUILD_REVISION
ENV XRAY_VERSION=${XRAY_VERSION} PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

RUN mkdir -p /etc/xray /data /opt/xray/site /opt/xray/scripts \
    && printf '%s\n' "$V89_BUILD_REVISION" > /tmp/v89-build-revision \
    && printf 'V89_DOCKER_SOURCE_MARKER=%s\n' "$V89_BUILD_REVISION"
COPY --from=xray /usr/local/bin/xray /usr/local/bin/xray
COPY scripts/ /opt/xray/scripts/
COPY web/site/ /opt/xray/site/
COPY --from=0 /tmp/v89-build-revision /opt/xray/.v89-build-revision

RUN chmod 0755 /usr/local/bin/xray /opt/xray/scripts/*.sh /opt/xray/scripts/*.py \
    && chmod -R a+rX /opt/xray/site

ENV PORT=8080 \
    PUBLIC_HTTP_PORT=8080 \
    XRAY_PORT=10087 \
    XRAY_HTTP_PORT=10086 \
    XRAY_LOGLEVEL=info \
    XRAY_READY_FILE=/data/.xray-ready \
    DATA_DIR=/data \
    XRAY_CONFIG=/etc/xray/config.json \
    REALITY_TARGET=www.cloudflare.com:443 \
    REALITY_SNI=www.cloudflare.com \
    REALITY_FINGERPRINT=chrome \
    XHTTP_PATH=/xhttp \
    XHTTP_MODE=auto \
    SHORT_ID=50175c035ee132 \
    SITE_DIR=/opt/xray/site \
    SUBSCRIPTION_FILE=/data/subscription.txt \
    SUBSCRIPTION_TOKEN_FILE=/data/subscription_token.txt

# Railway's PORT is the public gateway. The gateway multiplexes HTTP/subscription
# and TLS/REALITY, while Xray itself remains private on 10087.
EXPOSE 8080 10085 10087
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=5 CMD python3 -c "import os,urllib.request; p=os.getenv('PORT','8080'); urllib.request.urlopen('http://127.0.0.1:%s/health' % p, timeout=3).read()"

USER root
WORKDIR /opt/xray
ENTRYPOINT ["/opt/xray/scripts/start.sh"]
