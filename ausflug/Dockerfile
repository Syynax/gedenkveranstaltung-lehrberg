ARG BUILD_FROM
FROM ${BUILD_FROM}

ENV LANG=C.UTF-8 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt /tmp/requirements.txt

# --break-system-packages gibt es erst ab pip 23.0; auf älteren Basis-Images
# fällt der Aufruf auf die Variante ohne den Schalter zurück.
RUN apk add --no-cache python3 py3-pip \
 && ( pip3 install --no-cache-dir --break-system-packages -r /tmp/requirements.txt \
      || pip3 install --no-cache-dir -r /tmp/requirements.txt ) \
 && rm -f /tmp/requirements.txt

COPY rootfs /

RUN chmod a+x /app/run.sh

CMD [ "/app/run.sh" ]
