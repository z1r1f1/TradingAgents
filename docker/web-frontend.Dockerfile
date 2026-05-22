FROM node:24-alpine AS builder

WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
ARG VITE_TRADINGAGENTS_API=
ENV VITE_TRADINGAGENTS_API=${VITE_TRADINGAGENTS_API}
RUN npm run build

FROM nginx:1.27-alpine
COPY docker/web-nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=5 \
  CMD wget -qO- http://127.0.0.1/ >/dev/null
