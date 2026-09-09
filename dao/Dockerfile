# syntax=docker/dockerfile:1

FROM golang:1.23-alpine AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/dao ./cmd/dao

FROM alpine:3.20
RUN adduser -D -H -u 10001 app && apk add --no-cache wget
COPY --from=build /out/dao /usr/local/bin/dao
USER app
EXPOSE 8001
ENV DAO_ADDR=:8001
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=3 \
  CMD wget -qO- http://127.0.0.1:8001/healthz || exit 1
ENTRYPOINT ["/usr/local/bin/dao"]
