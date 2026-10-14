FROM node:24-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Public URL users open; SvelteKit's CSRF check compares form posts against it.
ARG PUBLIC_ORIGIN=http://localhost:8080
RUN PUBLIC_ORIGIN=$PUBLIC_ORIGIN npm run build && npm prune --omit=dev

FROM node:24-slim
WORKDIR /app
ENV NODE_ENV=production PORT=3000
COPY --from=build /app/build ./build
COPY --from=build /app/node_modules ./node_modules
COPY package.json .
USER node
EXPOSE 3000
HEALTHCHECK --interval=5s --timeout=3s --retries=10 \
    CMD node -e "fetch('http://127.0.0.1:3000/').then(r => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"
CMD ["node", "build"]
