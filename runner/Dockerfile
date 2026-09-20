# syntax=docker/dockerfile:1

FROM golang:1.27-bookworm AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/runner ./cmd/runner

FROM debian:bookworm-slim
# Toolchains for the supported languages. prlimit ships with util-linux (essential).
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      python3 gcc g++ libc6-dev nodejs tini ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && mkdir -p /sandbox && chmod 0711 /sandbox
COPY --from=build /out/runner /usr/local/bin/runner

# Runs as root so it can drop each execution to an unprivileged per-slot UID.
# The compose file drops all capabilities except the few needed for that.
# No port: the runner is a RabbitMQ consumer. RABBITMQ_URL (credentials) must
# come from the deployment, never from the image.
ENV RUNNER_SANDBOX_DIR=/sandbox \
    RUNNER_WORKERS=2 \
    RUNNER_QUEUE=judge.jobs \
    RUNNER_HEALTH_FILE=/tmp/runner-healthy
# Healthy while connected and consuming (heartbeat file younger than 20s).
HEALTHCHECK --interval=10s --timeout=4s --start-period=30s --retries=3 \
  CMD ["/usr/local/bin/runner", "healthcheck"]
# tini reaps orphaned grandchildren of sandboxed programs.
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/runner"]
