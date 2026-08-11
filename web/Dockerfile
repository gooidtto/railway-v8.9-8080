FROM python:3.12-alpine3.22
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
ENV PORT=8080 SITE_DIR=/opt/web/site DATA_DIR=/data
RUN mkdir -p /opt/web/site /data
COPY site/ /opt/web/site/
COPY server.py /opt/web/server.py
RUN chmod -R a+rX /opt/web/site
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3).read()"
WORKDIR /opt/web
CMD ["python3", "/opt/web/server.py"]
