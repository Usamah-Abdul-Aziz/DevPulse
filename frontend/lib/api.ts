/**
 * Thin API client.
 *
 * Requests go to /api/... which Next.js rewrites to the backend
 * (next.config.ts), so components never hard-code an origin and work
 * identically on Vercel and in Docker.
 */

import type {
  ConnectResponse,
  HealthResponse,
  JobResponse,
  Page,
  ReadinessResponse,
  RepositorySummary,
} from "@/types";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public detail?: string,
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
    // Errors are RFC 9457 problem documents (docs/api.md); surface `detail`, not a status dump.
    const body = (await response.json().catch(() => null)) as {
      detail?: string;
      title?: string;
    } | null;
    throw new ApiError(
      response.status,
      body?.detail ?? body?.title ?? `${response.status} ${response.statusText} — ${path}`,
      body?.detail,
    );
  }

  return response.json() as Promise<T>;
}

export const api = {
  health: () => request<HealthResponse>("/api/v1/healthz"),
  readiness: () => request<ReadinessResponse>("/api/v1/readyz"),
  listRepositories: (page = 1, limit = 20) =>
    request<Page<RepositorySummary>>(
      `/api/v1/repositories?page=${page}&limit=${limit}`,
    ),
  connectRepository: (repository: string) =>
    request<ConnectResponse>("/api/v1/repositories/connect", {
      method: "POST",
      body: JSON.stringify({ repository }),
    }),
  getJob: (jobId: number) => request<JobResponse>(`/api/v1/jobs/${jobId}`),
};
