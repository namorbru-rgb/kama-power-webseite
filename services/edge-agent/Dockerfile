FROM golang:1.22-alpine AS builder
RUN apk add --no-cache gcc musl-dev sqlite-dev
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=1 go build -o /edge-agent ./...

FROM alpine:3.19
RUN apk add --no-cache sqlite-libs ca-certificates
RUN adduser -D -u 1000 kama
USER kama
WORKDIR /app
COPY --from=builder /edge-agent .
VOLUME ["/var/lib/kama-edge", "/etc/kama-edge"]
ENTRYPOINT ["/app/edge-agent"]
CMD ["--config", "/etc/kama-edge/config.yaml"]
