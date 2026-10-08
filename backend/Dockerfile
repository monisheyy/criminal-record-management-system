# AI-CRMS API image. Production-style: no --reload, non-root user, healthcheck.
FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY alembic.ini seed_data.py ./
COPY app ./app
COPY migrations ./migrations
COPY scripts ./scripts

RUN useradd --system --uid 10001 --home /app crms \
    && mkdir -p /var/lib/ai-crms/models /var/lib/ai-crms/uploads \
    && chown -R crms /var/lib/ai-crms /app/app/ml/saved_models
USER crms

ENV AI_CRMS_MODEL_DIR=/var/lib/ai-crms/models \
    AI_CRMS_UPLOAD_DIR=/var/lib/ai-crms/uploads
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health/ready', timeout=4).status == 200 else 1)"

# --proxy-headers: trust X-Forwarded-* from the nginx reverse proxy in front.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*", "--workers", "2"]
