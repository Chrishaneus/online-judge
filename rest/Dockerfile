# syntax=docker/dockerfile:1

FROM golang:1.23-alpine AS build
WORKDIR /src
COPY go.mod ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/rest ./cmd/rest

# The binary has no dependencies and ships its own healthcheck subcommand.
FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=build /out/rest /rest
EXPOSE 8000
ENV REST_ADDR=:8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 CMD ["/rest", "healthcheck"]
ENTRYPOINT ["/rest"]
