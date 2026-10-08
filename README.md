# DevPulse

**AI-Powered Software Engineering Intelligence Platform**

DevPulse analyzes software-development activity from public GitHub repositories and uses
analytics + machine learning to surface project health, delivery risks, and engineering
bottlenecks — with explanations a tech lead can act on.

> **Status:** Phase 0 (product definition) complete · Phases 1–8 = MVP · in development

---

## Problem

Raw Git activity does not answer the questions engineering leads actually ask:

- Is the project healthy, and is delivery getting slower?
- Which open Pull Requests are risky, and why?
- Are reviews becoming a bottleneck?
- Is knowledge or workload overly concentrated?
- Which areas should we investigate first?

## Solution

DevPulse is a **decision-support platform**, not a GitHub dashboard. For a repository it computes:

1. **Engineering metrics** — PR cycle time decomposed into pickup / review / merge delay, code
   churn, PR size, contributor concentration, issue health, CI success rate
   ([docs/metrics.md](docs/metrics.md)).
2. **Project Health Score** — a rule-based, transparent 0–100 score with six weighted components
   and a full breakdown of how it was computed.
3. **PR risk prediction** — at the moment a PR is opened, an XGBoost model estimates the likelihood
   of post-merge rework or regression, with SHAP-based per-PR explanations. It is benchmarked
   against a rule-based baseline, and the comparison is reported honestly.

## Architecture

```text
GitHub (public repos) → async ingestion → PostgreSQL
   → feature engineering (as-of snapshots)
   → analytics (metrics, health) + ML (offline training, batch scoring)
   → FastAPI read API → Next.js dashboard
```

- **Training is offline** in `ml/`; the backend only loads a versioned artifact and scores in
  batch. Predictions and SHAP are stored, never computed live per request.
- **Ingestion is asynchronous** (job table + background tasks). No queue/Redis unless justified by
  a written decision.

Full design: [docs/architecture.md](docs/architecture.md).

## ML pipeline

- **Label:** a PR is `high_risk` if, within 14 days after merge, it is reverted or followed by a
  same-file fix PR linked to a bug — a documented SZZ-lite heuristic (label noise is expected and
  stated in the UI).
- **Features:** size, file history, author history, and context — **all as-of PR creation time**,
  enforced by an automated leakage test (`test_features_are_as_of`).
- **Dataset:** 20 public repositories across languages and sizes
  ([ADR-001](docs/decisions/ADR-001-training-repositories.md)), versioned snapshots.
- **Evaluation:** time-based split + cross-repo holdout; PR-AUC (primary), precision@k/recall@k,
  Brier score and calibration curve; the rule baseline is the model to beat.

Details: [docs/ml.md](docs/ml.md).

## Evaluation

<!-- Numbers below are filled in by Phase 7's evaluation report. Do not edit by hand. -->

| Model | PR-AUC | ROC-AUC | Precision@k | Recall@k | Positive rate |
|---|---|---|---|---|---|
| Rule baseline | _pending_ | — | _pending_ | _pending_ | _pending_ |
| Logistic Regression | _pending_ | _pending_ | _pending_ | _pending_ | _pending_ |
| Random Forest | _pending_ | _pending_ | _pending_ | _pending_ | _pending_ |
| XGBoost | _pending_ | _pending_ | _pending_ | _pending_ | _pending_ |

_Every value in this table is produced by a reproducible script and measured on real data. Values
are `pending` until Phase 7; no number above is a claim about model quality yet._

## Features

**MVP:** repository ingestion · engineering metrics · Project Health Score · rule-based risk
baseline · ML PR risk + SHAP · pre-computed demo repository

**Post-MVP:** code hotspots · anomaly detection · delivery-delay prediction · recommendation
engine · observability/MLOps-lite

## Tech stack

| Layer | Choice |
|---|---|
| Frontend | Next.js · TypeScript · Tailwind CSS · shadcn/ui · Recharts |
| Backend | Python · FastAPI · Pydantic · SQLAlchemy · Alembic · httpx |
| Database | PostgreSQL (Supabase) |
| Data / ML | pandas · NumPy · scikit-learn · XGBoost · SHAP · joblib |
| Testing | pytest · Vitest |
| CI/CD · Deploy | GitHub Actions · Vercel · Render · Supabase |

## Documentation

- [Product spec](docs/product.md) — vision, scope, non-goals, metrics, health score, demo mode
- [Architecture](docs/architecture.md) — system design, data model, API, deployment
- [ML](docs/ml.md) — labels, as-of features, evaluation protocol, SHAP
- [Metrics](docs/metrics.md) — health thresholds and their validation status
- [API](docs/api.md) — endpoint contracts and conventions
- [Deployment](docs/deployment.md) — local, Vercel/Render/Supabase, runbooks, free-tier checks
- [Roadmap](docs/roadmap.md) — phases and acceptance criteria
- [Decisions](docs/decisions/) — architecture decision records
- [AGENTS.md](AGENTS.md) — guidance for AI coding agents

## Deployment

```text
Frontend → Vercel · Backend → Render · Database → Supabase
```

Target: free-tier hosting for development and the portfolio demo. Free-tier limits are verified
during Phase 1 per [ADR-007](docs/decisions/ADR-007-hosting-plan.md); the fallback ladder is a
cheap VPS (no code change) and then a managed DB. Public deployment claims are made only after
those checks are recorded.

## Limitations

- **Label noise:** the risk label is a heuristic approximation of "caused rework", not ground truth.
- **Public repositories only** in v1; no OAuth login (a read-only server-side token + allow-list).
- **Free-tier constraints:** backend sleeps when idle, database has storage/egress caps — the demo
  is pre-computed to stay fast through cold starts.
- **Health thresholds are initial values**, validated during Phase 4
  ([docs/metrics.md](docs/metrics.md)).
- **Not a developer-performance tool.** Contributor views show workload concentration as a team
  risk signal; there are no leaderboards and no individual scores.

## Future work

GitLab support · private repos + OAuth · webhooks/real-time · code hotspots · anomaly detection ·
delivery-delay prediction · recommendation engine

## License

MIT
