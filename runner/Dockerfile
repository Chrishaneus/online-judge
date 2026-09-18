# syntax=docker/dockerfile:1

FROM golang:1.23-bookworm AS build
WORKDIR /src
COPY go.mod ./
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
ENV RUNNER_ADDR=:8002 \
    RUNNER_SANDBOX_DIR=/sandbox \
    RUNNER_WORKERS=2
EXPOSE 8002
HEALTHCHECK --interval=10s --timeout=4s --start-period=10s --retries=3 \
  CMD ["/usr/local/bin/runner", "healthcheck"]
# tini reaps orphaned grandchildren of sandboxed programs.
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/runner"]
