# syntax=docker/dockerfile:1

FROM golang:1.27-bookworm AS build
WORKDIR /src
ENV CGO_ENABLED=0 GOTOOLCHAIN=local
COPY go.mod go.sum ./
RUN --mount=type=cache,target=/go/pkg/mod go mod download
COPY . .
RUN --mount=type=cache,target=/go/pkg/mod --mount=type=cache,target=/root/.cache/go-build \
    go build -trimpath -ldflags="-s -w" -o /out/dao ./cmd/dao

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=build /out/dao /usr/local/bin/dao
USER nonroot:nonroot
ENV DAO_ADDR=:50052
EXPOSE 50052
# Calls grpc.health.v1.Health/Check on DAO_ADDR; SERVING iff the DB is reachable.
HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=3 \
  CMD ["/usr/local/bin/dao", "healthcheck"]
ENTRYPOINT ["/usr/local/bin/dao"]
