# Stage 1: Install dependencies
FROM node:18-alpine AS deps
WORKDIR /app
RUN npm install -g pnpm
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

# Stage 2: Build the application
FROM node:18-alpine AS builder
WORKDIR /app
COPY --from=deps /usr/local/lib/node_modules/pnpm /usr/local/lib/node_modules/pnpm
RUN ln -s /usr/local/lib/node_modules/pnpm/bin/pnpm.cjs /usr/local/bin/pnpm
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN pnpm build

# Stage 3: Production runner
FROM node:18-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production

COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000

CMD ["node", "server.js"]
