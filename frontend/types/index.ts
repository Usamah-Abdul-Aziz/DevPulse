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
