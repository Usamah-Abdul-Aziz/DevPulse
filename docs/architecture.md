# DevPulse — Architecture

This document describes *how* DevPulse is built. What it does is in
[`product.md`](product.md); the ML system in [`ml.md`](ml.md); the schedule in
[`roadmap.md`](roadmap.md).

---

## 1. System architecture

```text
                        ┌───────────────┐
                        │  GitHub API   │
                        │ (GraphQL+REST)│
                        └───────┬───────┘
                                ▼
                    ┌──────────────────────┐
                    │ Ingestion Service    │
                    │ async jobs, cursors, │
                    │ rate-limit handling  │
                    └──────────┬───────────┘
                               ▼
                    ┌──────────────────────┐
                    │ PostgreSQL           │
                    │ raw + normalized     │
                    │ + feature snapshots  │
                    └──────────┬───────────┘
              ┌────────────────┴────────────────┐
              ▼                                 ▼
   ┌────────────────────┐            ┌─────────────────────┐
   │ Analytics Engine   │            │ ML Pipeline         │
   │ metrics, health,   │            │ offline training    │
   │ trends             │            │ batch scoring+SHAP  │
   └─────────┬──────────┘            └──────────┬──────────┘
             └─────────────────┬────────────────┘
                               ▼
                    ┌──────────────────────┐
                    │ FastAPI (read API)   │
                    └──────────┬───────────┘
                               ▼
                    ┌──────────────────────┐
                    │ Next.js Frontend     │
                    └──────────────────────┘
```

### Key decisions

- **Training is offline** (notebooks / scripts in `ml/`). The backend only loads a versioned model
  artifact for **batch scoring**; predictions and SHAP values are stored in the database and served
  as plain reads.
- **Ingestion is asynchronous from day one** (job table + FastAPI background tasks). A lightweight
  queue (RQ/Celery + Redis) is introduced only if background tasks prove insufficient — adding any
  infrastructure requires a written ADR in `docs/decisions/` stating the reason.
- Free-tier hosts have small memory; do not run SHAP or model training inside a request.

## 2. Tech stack

| Layer | Choice |
|---|---|
| Frontend | Next.js, TypeScript, Tailwind CSS, shadcn/ui, Recharts |
| Backend | Python, FastAPI, Pydantic, SQLAlchemy, Alembic, httpx |
| Database | PostgreSQL (Supabase for deployment) |
| Data / ML | pandas, NumPy, scikit-learn, XGBoost, SHAP, joblib |
| Dev | Git, GitHub, Docker, Docker Compose, VS Code |
| Testing | pytest, Vitest, Playwright (optional) |
| CI/CD | GitHub Actions |
| Deploy | Vercel Hobby (frontend), Render Free (backend), Supabase Free (database) |

Only add technology with a stated reason. Redis, Kafka, and webhooks are explicitly post-MVP.

## 3. Repository structure

```text
devpulse/
├── frontend/            app/ components/ lib/ hooks/ types/
├── backend/
│   ├── app/
│   │   ├── api/ core/ models/ schemas/ services/ repositories/
│   │   ├── analytics/   metrics + health score (+ health_config.yaml)
│   │   ├── ingestion/   GitHub clients, jobs, cleaning
│   │   └── ml/          INFERENCE ONLY: load model, batch score, SHAP
│   ├── tests/
│   └── requirements.txt
├── ml/                  TRAINING & EVALUATION
│   ├── notebooks/ datasets/ labeling/ features/ training/ evaluation/
│   └── models/          versioned artifacts (small) or pointer to storage
├── docs/                product.md architecture.md ml.md metrics.md api.md decisions/
├── docker/
├── .github/workflows/   backend.yml frontend.yml ml.yml
├── docker-compose.yml
├── README.md
└── AGENTS.md
```

**Boundary:** `ml/` trains and evaluates; `backend/app/ml/` only loads a versioned artifact and
scores. Feature code shared by both lives in one package imported by both, so training and serving
cannot drift apart.

## 4. Data model

Initial entities (all repo-scoped tables carry `repository_id`):

| Table | Key columns / constraints |
|---|---|
| `repositories` | `owner`, `name` (unique together), `default_branch`, `last_synced_at`, `is_demo` |
| `contributors` | `repository_id`, `login`, `is_bot`, merged identities (email/login aliases) |
| `commits` | `sha` (unique per repo), `author_id`, `committed_at`, `additions`, `deletions`, `is_merge` |
| `pull_requests` | unique (`repository_id`, `number`); `created_at`, `merged_at`, `closed_at`, `is_draft`, additions, deletions, `changed_files`, `base_branch` |
| `pull_request_reviews` | `pull_request_id`, `reviewer_id`, `state`, `submitted_at` |
| `issues` | unique (`repository_id`, `number`); `created_at`, `closed_at`, labels, `reopened_count` |
| `file_changes` | `pull_request_id` / `commit_id`, `path`, additions, deletions, `is_generated` |
| `ci_runs` | `repository_id`, `workflow`, `branch`, `conclusion`, `started_at`, `completed_at` |
| `releases` | `repository_id`, `tag`, `published_at` |
| `ingestion_jobs` | `repository_id`, `status`, `started_at`, `finished_at`, `cursor`, `error`, counts |
| `metrics` | `repository_id`, `metric_key`, `window_start`, `window_end`, `value` (p50/p85 stored as separate keys) |
| `pr_features` | `pull_request_id`, `feature_version`, `as_of` (= PR `created_at`), feature columns / JSONB |
| `risk_predictions` | `pull_request_id`, `model_version_id`, `score`, `tier`, `shap` (JSONB: feature → signed contribution), `scored_at` |
| `hotspots` | `repository_id`, `path`, `score`, `computed_at` |
| `anomalies` | `repository_id`, `metric_key`, `window`, `expected`, `observed`, `method` |
| `model_versions` | `name`, `version`, `dataset_version`, `metrics` (JSONB), `artifact_path`, `is_production` |

Also: store the raw GitHub payload (JSONB) for PRs so re-extraction does not require re-fetching;
add indexes on (`repository_id`, `created_at`) for time-series queries. `users` is deferred with
OAuth ([product.md §4.2](product.md#42-non-goals-for-v1)).

## 5. Ingestion design

Input: `owner/repository` (public, from an allow-list in v1).

1. **API strategy:** prefer the GraphQL API for PRs + reviews + files in fewer calls; use REST for
   CI runs and releases. Avoid N+1 requests per PR.
2. **Rate limits:** read rate-limit headers, back off with jitter, and stop the job cleanly when
   the budget is exhausted (resume from a stored cursor).
3. **Incremental sync:** after the first full sync, fetch only items updated since
   `last_synced_at` (cursor / `since` / ETag).
4. **Jobs:** `POST /connect` creates an `ingestion_jobs` row and returns immediately; the UI polls
   job status.
5. **Size limits:** history depth capped per [ADR-006](decisions/ADR-006-history-depth-cap.md)
   (24 months; 12 months for very large repos) to stay within free-tier limits.
6. **Cleaning:** flag bots, mark generated files, merge author identities, handle deleted
   ("ghost") users.
7. **Label inputs:** also fetch revert references, issue links (`fixes #n`), and issue labels
   needed by [`ml.md` §2](ml.md#2-label-definition).

**Acceptance:** a medium public repository can be ingested end-to-end, re-run idempotently, and
resumed after a simulated rate-limit stop.

## 6. API design

```text
# Repositories & ingestion
GET   /api/v1/repositories
POST  /api/v1/repositories/connect                 → 202 + job id
GET   /api/v1/jobs/{job_id}                        → ingestion status
GET   /api/v1/repositories/{id}

# Analytics
GET   /api/v1/repositories/{id}/metrics?window=
GET   /api/v1/repositories/{id}/activity
GET   /api/v1/repositories/{id}/health
GET   /api/v1/repositories/{id}/contributors

# Pull requests & risk
GET   /api/v1/repositories/{id}/pull-requests?risk=&state=&page=
GET   /api/v1/repositories/{id}/risks
GET   /api/v1/pull-requests/{id}
GET   /api/v1/pull-requests/{id}/risk              → score, tier, SHAP contributions

# Post-MVP
GET   /api/v1/repositories/{id}/hotspots
GET   /api/v1/repositories/{id}/anomalies

# Operational
GET   /api/v1/demo                                 → demo repository summary
GET   /healthz
```

All list endpoints are paginated; hotspots and anomalies are repository-scoped (consistent with the
frontend routes). Contract details are documented in `api.md` as endpoints are implemented.

## 7. Frontend routes

```text
/                                  landing + [ Try Live Demo ]
/dashboard
/repositories
/repositories/[id]                 overview (health, key metrics, activity)
/repositories/[id]/pull-requests
/repositories/[id]/pull-requests/[number]   PR detail + risk explanation
/repositories/[id]/contributors
/repositories/[id]/risks
/repositories/[id]/hotspots        (post-MVP)
/repositories/[id]/anomalies       (post-MVP)
/settings
```

`/login` is deferred. Prioritize clarity over visual complexity; validate each screen against the
Monday-triage scenario.

## 8. Testing and CI/CD

**Backend (pytest):** API endpoints, DB operations, metric calculations (with fixed fixtures),
ingestion (mocked GitHub), batch scoring.

**Frontend (Vitest):** components and data formatting; Playwright optional for the demo flow.

**ML tests:**

```text
test_features_are_as_of        no feature uses data after PR created_at
test_label_rules               label heuristic on hand-built fixtures
test_feature_pipeline          schema, nulls, determinism
test_model_prediction          output range and tier mapping
test_prediction_schema         API response contract
test_model_version             artifact ↔ model_versions consistency
```

**Pipeline:** Push → Lint → Unit tests → Build → Deploy (separate `backend.yml`,
`frontend.yml`, `ml.yml`).

## 9. Observability (post-MVP, lightweight first)

Track: API logs, ingestion job status and errors, model version used for each prediction, and
scoring runs. A simple internal status page (API, database, GitHub API, last ingestion, current
model version) is enough. Drift monitoring is justified only when there is enough ongoing data to
make it meaningful.

## 10. Deployment

```text
Frontend → Vercel Hobby
Backend  → Render Free
Database → Supabase Free
```

Target: **Rp0 for development and the portfolio demo**, within free-tier limits. Free-tier limits
are verified during Phase 1 per [ADR-007](decisions/ADR-007-hosting-plan.md), which also defines
the fallback ladder (cheap VPS → managed DB). No public deployment promise is made until those
checks are recorded.

## 11. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Too few / noisy positive labels | Weak or misleading model | Multi-repo dataset; documented label rules; minimum-positives threshold; report positive rate |
| Data leakage | Inflated metrics | As-of feature pipeline + automated leakage test; time-based split |
| GitHub rate limits | Slow or failed ingestion | GraphQL, incremental sync, cursors, capped history, pre-ingested demo |
| Free-tier cold start / pause | Poor first impression | Pre-computed demo, skeleton UI, verify current limits |
| Memory limits on free host | Crashes | Offline training, batch scoring, no live SHAP |
| Arbitrary health thresholds | Untrustworthy score | Config file, documented thresholds, validation on known repos |
| Scope creep | Never reaches demo | MVP = Phases 0–8; post-MVP only after MVP is stable |
| Misinterpretation of signals | Blaming individuals | Aggregate views, explicit wording ("signal to investigate") |
