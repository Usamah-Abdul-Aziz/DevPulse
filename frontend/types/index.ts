/**
 * Shared types for the DevPulse frontend.
 *
 * These mirror the backend Pydantic schemas (docs/architecture.md §6). The
 * contract test in the backend asserts they stay in sync.
 */

export type HealthStatus = "ok" | "fail";

export interface HealthResponse {
  status: HealthStatus;
  service: string;
  version: string;
  environment: string;
}

export interface ReadinessComponent {
  name: string;
  status: HealthStatus;
  detail?: string | null;
}

export interface ReadinessResponse {
  status: HealthStatus;
  service: string;
  version: string;
  components: ReadinessComponent[];
}

/** Risk tiers, derived from calibrated thresholds (ADR-005). */
export type RiskTier = "LOW" | "MEDIUM" | "HIGH";

export interface RiskPrediction {
  pullRequestId: number;
  score: number;
  tier: RiskTier;
  /** feature name -> signed SHAP contribution */
  shap: Record<string, number>;
  scoredAt: string;
}

/** Bands for the health score (docs/metrics.md §1). */
export type HealthBand = "healthy" | "watch" | "at-risk";

export interface HealthComponent {
  name: string;
  score: number;
  weight: number;
  excluded: boolean;
}

/**
 * Phase 2: ingestion.
 *
 * Field names mirror the backend JSON verbatim (Pydantic's default, snake_case). `JobStatus`
 * mirrors the CHECK constraint on `ingestion_jobs.status`; the polling hook stops when the
 * status leaves the non-terminal set.
 */
export type JobStatus = "pending" | "running" | "paused" | "succeeded" | "failed";

export const JOB_TERMINAL_STATUSES: readonly JobStatus[] = ["succeeded", "failed"] as const;

export interface IngestionCounts {
  prs?: number;
  reviews?: number;
  issues?: number;
  commits?: number;
  files?: number;
  releases?: number;
  contributors?: number;
  api_calls?: number;
}

export interface IngestionCursor {
  phase: string;
  cursors?: Record<string, string | null>;
  window_start?: string | null;
  window_end?: string | null;
  history_months?: number;
  mode?: string;
}

export interface JobResponse {
  id: number;
  repository_id: number;
  status: JobStatus;
  started_at?: string | null;
  finished_at?: string | null;
  resume_after?: string | null;
  cursor?: IngestionCursor | null;
  counts?: IngestionCounts | null;
  error?: string | null;
}

export interface LatestJobSummary {
  id: number;
  status: JobStatus;
  started_at?: string | null;
  finished_at?: string | null;
  resume_after?: string | null;
  counts?: IngestionCounts | null;
  error?: string | null;
}

export interface RepositorySummary {
  id: number;
  full_name: string;
  owner: string;
  name: string;
  default_branch?: string | null;
  last_synced_at?: string | null;
  is_demo: boolean;
}

export interface RepositoryDetail extends RepositorySummary {
  latest_job?: LatestJobSummary | null;
}

export interface ConnectResponse {
  job_id: number;
  repository_id: number;
  status: JobStatus;
}

export interface Page<T> {
  items: T[];
  page: number;
  limit: number;
  total: number;
}
