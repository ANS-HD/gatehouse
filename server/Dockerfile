FROM python:3.12-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f AS dependencies

ENV VIRTUAL_ENV=/opt/venv PATH="/opt/venv/bin:$PATH"
RUN python -m venv "$VIRTUAL_ENV"
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock

FROM python:3.12-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"
WORKDIR /app

COPY --from=dependencies /opt/venv /opt/venv
COPY app ./app

RUN /usr/local/bin/python -m pip uninstall -y pip setuptools wheel \
    && rm -rf /opt/venv/lib/python3.12/site-packages/pip* /opt/venv/bin/pip* \
    && useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin gateway \
    && mkdir -p /data \
    && chown gateway:gateway /data
USER gateway

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
