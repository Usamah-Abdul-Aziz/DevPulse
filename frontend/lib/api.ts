/**
 * Thin API client.
 *
 * Requests go to /api/... which Next.js rewrites to the backend
 * (next.config.ts), so components never hard-code an origin and work
 * identically on Vercel and in Docker.
 */

import type { HealthResponse, ReadinessResponse } from "@/types";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
    // Next.js fetch caches aggressively by default; dashboard data must be live.
    cache: "no-store",
  });

  if (!response.ok) {
    throw new ApiError(response.status, `${response.status} ${response.statusText} — ${path}`);
  }

  return response.json() as Promise<T>;
}

export const api = {
  health: () => request<HealthResponse>("/api/v1/healthz"),
  readiness: () => request<ReadinessResponse>("/api/v1/readyz"),
};
