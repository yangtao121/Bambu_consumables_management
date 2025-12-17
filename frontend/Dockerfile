FROM node:20-alpine AS deps

WORKDIR /app

COPY package*.json /app/
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi


FROM node:20-alpine AS builder

WORKDIR /app

COPY --from=deps /app/node_modules /app/node_modules
COPY . /app

ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build


FROM node:20-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

COPY --from=builder /app/package.json /app/package.json
COPY --from=builder /app/docker-entrypoint.sh /app/docker-entrypoint.sh
COPY --from=builder /app/.next /app/.next
COPY --from=deps /app/node_modules /app/node_modules

# Drop devDependencies for smaller runtime image (best-effort).
RUN npm prune --omit=dev || true

RUN chmod +x /app/docker-entrypoint.sh && mkdir -p /app/public

EXPOSE 3000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["npm", "run", "start", "--", "-H", "0.0.0.0", "-p", "3000"]


