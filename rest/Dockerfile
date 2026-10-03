# syntax=docker/dockerfile:1

FROM golang:1.27-bookworm AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN --mount=type=cache,target=/go/pkg/mod go mod download
COPY . .
RUN --mount=type=cache,target=/go/pkg/mod --mount=type=cache,target=/root/.cache/go-build \
    CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/rest ./cmd/rest

# The binary has no dependencies and ships its own healthcheck subcommand.
FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=build /out/rest /rest
EXPOSE 8000
ENV REST_ADDR=:8000 \
    MIDLAYER_ADDR=midlayer:50051
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 CMD ["/rest", "healthcheck"]
ENTRYPOINT ["/rest"]
