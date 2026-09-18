FROM ghcr.io/home-assistant/base:latest

RUN \
    apk add --no-cache \
        python3 \
        py3-pip

COPY requirements.txt /app/requirements.txt

RUN pip3 install --no-cache-dir -r /app/requirements.txt

COPY run.py /app/run.py
COPY run.sh /run.sh

RUN chmod a+x /run.sh

CMD ["/run.sh"]
