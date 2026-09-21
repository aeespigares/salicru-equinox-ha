FROM ghcr.io/home-assistant/base:3.24-2026.08.0

RUN \
    apk add --no-cache \
        python3 \
        py3-pip \
        python3-dev

RUN \
    python3 -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir paho-mqtt

COPY run.py /app/run.py
COPY run.sh /run.sh

RUN chmod a+x /run.sh

CMD ["/run.sh"]
