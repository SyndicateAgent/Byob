FROM node:20-alpine AS deps

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

FROM node:20-alpine AS builder

WORKDIR /app/frontend
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
ARG NEXT_PUBLIC_MINIO_CONSOLE_URL=http://localhost:9001
ARG NEXT_PUBLIC_QDRANT_DASHBOARD_URL=http://localhost:6333/dashboard
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL \
    NEXT_PUBLIC_MINIO_CONSOLE_URL=$NEXT_PUBLIC_MINIO_CONSOLE_URL \
    NEXT_PUBLIC_QDRANT_DASHBOARD_URL=$NEXT_PUBLIC_QDRANT_DASHBOARD_URL
COPY --from=deps /app/frontend/node_modules ./node_modules
COPY frontend ./
COPY docs ../docs
RUN npm run build

FROM node:20-alpine AS runner

WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000

COPY --from=builder /app/frontend/.next/standalone ./
COPY --from=builder /app/frontend/.next/static ./.next/static

CMD ["node", "server.js"]
