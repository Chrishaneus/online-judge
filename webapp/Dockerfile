# syntax=docker/dockerfile:1

# Run the unit tests as part of the build so a broken frontend never ships.
FROM node:22-alpine AS test
WORKDIR /app
COPY package.json ./
COPY public ./public
COPY tests ./tests
RUN npm test

FROM nginxinc/nginx-unprivileged:1.27-alpine
ENV REST_UPSTREAM=http://rest:8000
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=test /app/public /usr/share/nginx/html
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -qO- http://127.0.0.1:8080/healthz >/dev/null || exit 1
