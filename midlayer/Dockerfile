# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app

# uid/gid 10001 must match RUNNER_SOCKET_GID so we can use the runner's unix socket.
RUN groupadd -g 10001 app && useradd -u 10001 -g app -M -s /usr/sbin/nologin app
USER app

EXPOSE 8003
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8003/healthz', timeout=2).status == 200 else 1)"

# A single process: the judge queue lives in memory, so don't add --workers.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003", "--no-access-log"]
