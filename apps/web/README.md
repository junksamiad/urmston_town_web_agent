This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.

## Backend API Configuration

This frontend application needs to connect to a backend API. The URL for this API is configured differently depending on the environment:

### 1. Local Development (outside Docker)

-   **File:** `apps/web/.env.local` (This file should be in your `.gitignore`)
-   **Variable:** `NEXT_PUBLIC_API_URL`
-   **Example Value:** `NEXT_PUBLIC_API_URL=http://localhost:8000`
-   **How it works:** When you run `pnpm dev`, Next.js automatically loads variables from `.env.local`. The application code (`src/app/chat/page.tsx`) uses `process.env.NEXT_PUBLIC_API_URL` and falls back to `http://localhost:8000` if the variable isn't set.

### 2. Docker Development (with Docker Compose)

-   **File:** `../../docker-compose.yml` (in the project root)
-   **Variable:** `NEXT_PUBLIC_API_URL` (set under the `frontend` service's `environment` section)
-   **Example Value:** `NEXT_PUBLIC_API_URL: http://backend:8000`
-   **How it works:** Docker Compose injects this environment variable into the frontend container. The `backend` hostname refers to the backend service defined in `docker-compose.yml`, and Docker's internal networking resolves it to the backend container's IP address.

### 3. Production Deployment (e.g., AWS, Vercel)

-   **Method:** Set environment variables through your deployment platform's settings.
-   **Variable:** `NEXT_PUBLIC_API_URL`
-   **Example Value:** `NEXT_PUBLIC_API_URL=https://your-live-backend-api.com`
-   **How it works:** The deployed Next.js application will pick up this environment variable provided by the hosting platform.

This setup allows the frontend to connect to the correct backend API URL without needing code changes for different environments. The key is the `NEXT_PUBLIC_API_URL` environment variable, which is set appropriately for each context.
