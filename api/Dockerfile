# syntax=docker/dockerfile:1
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY migrations ./migrations
COPY wsgi.py gunicorn.conf.py ./

RUN groupadd -g 10001 app && useradd -u 10001 -g app -M -s /usr/sbin/nologin app
USER 10001:10001

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=3 \
  CMD ["python", "-m", "app.healthcheck"]

# Apply pending migrations (advisory-locked, waits for Postgres), then serve: one gthread worker
# process with API_THREADS threads (the rate limiter is in process memory), access log on stdout.
# The worker uses the same image: command ["python", "-m", "app.worker"].
CMD ["sh", "-c", "flask --app wsgi migrate && exec gunicorn -c gunicorn.conf.py wsgi:app"]
