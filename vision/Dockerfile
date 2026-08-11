ARG XRAY_VERSION=26.3.27
FROM ghcr.io/xtls/xray-core:${XRAY_VERSION} AS xray
FROM python:3.12-alpine3.22
ARG XRAY_VERSION
ENV XRAY_VERSION=${XRAY_VERSION} PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN mkdir -p /etc/xray /data /opt/xray
COPY --from=xray /usr/local/bin/xray /usr/local/bin/xray
COPY start.sh /opt/xray/start.sh
COPY generate.py /opt/xray/generate.py
COPY health.py /opt/xray/health.py
RUN chmod 0755 /usr/local/bin/xray /opt/xray/*.sh /opt/xray/*.py
ENV PORT=8080 XRAY_PORT=8080 PROTOCOL=vision XRAY_LOGLEVEL=info DATA_DIR=/data XRAY_CONFIG=/etc/xray/config.json
ENV REALITY_TARGET=www.cloudflare.com:443 REALITY_SNI=www.cloudflare.com REALITY_FINGERPRINT=chrome
ENV SHORT_ID=50175c035ee132
ENV VLESS_FLOW=xtls-rprx-vision
ENV XHTTP_PATH=/xhttp XHTTP_MODE=auto
EXPOSE 8080
USER root
WORKDIR /opt/xray
ENTRYPOINT ["/opt/xray/start.sh"]
