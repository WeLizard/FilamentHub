FROM python:3.12-alpine

RUN apk add --no-cache openssl \
    && install -d -m 0755 /run/adapter-lab \
    && openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
        -subj "/CN=filamenthub-adapter-lab" \
        -keyout /run/adapter-lab/bambu.key \
        -out /run/adapter-lab/bambu.crt \
    && chown nobody:nobody /run/adapter-lab/bambu.key /run/adapter-lab/bambu.crt \
    && chmod 0400 /run/adapter-lab/bambu.key \
    && chmod 0444 /run/adapter-lab/bambu.crt

WORKDIR /app
COPY moonraker_hh.py bambu_lan.py ./

USER nobody
