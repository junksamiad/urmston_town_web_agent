# 1. Use an official Node.js 20 LTS image as a parent image
FROM node:20-slim AS base

# Set the working directory in the container
WORKDIR /app

# 2. Dependency Installation Stage
FROM base AS deps
# Copy package.json and pnpm-lock.yaml
COPY package.json pnpm-lock.yaml* ./
# Copy .pnpmfile.cjs if it exists (it's good practice to include)
COPY .pnpmfile.cjs* ./

# Install pnpm globally
RUN npm install -g pnpm

# Install dependencies using pnpm
# --frozen-lockfile ensures we use exact versions from pnpm-lock.yaml
RUN pnpm install --frozen-lockfile

# 3. Build Stage
FROM deps AS builder
COPY --from=deps /app/node_modules /app/node_modules
COPY . .
# Build the Next.js application
RUN pnpm build

# 4. Production Stage
FROM base AS runner
WORKDIR /app

ENV NODE_ENV production
# Optionally, set a different port if your app runs on something other than 3000
# ENV PORT 3000

# Copy the built app from the builder stage
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

# Expose the port the app runs on
EXPOSE 3000

# The command to run when the container starts
# Using the standalone output of Next.js
CMD ["node", "server.js"] 