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

Implemented in Phase 1 + Phase 2 (`backend/app/models/`, one file per entity group; all repo-scoped
tables carry `repository_id`; timestamps are `DateTime(timezone=True)`):

| Table | Natural key (unique) | Key columns |
|---|---|---|
| `repositories` | `(owner, name)` | `default_branch`, `last_synced_at`, `is_demo` |
| `contributors` | `(repository_id, github_id)` | `login`, `name`, `email`, `is_bot`, `is_ghost` — keyed on the GraphQL node id, not the mutable login ([ADR-010](decisions/ADR-010-contributor-identity-and-ghosts.md)) |
| `pull_requests` | `(repository_id, number)` | `title`, `state`, `author_id`, `created_at`, `updated_at`, `closed_at`, `merged_at`, `is_draft`, `additions`, `deletions`, `changed_files`, `base_branch`, `head_branch`, `labels` (JSONB), `raw_payload` (JSONB), `truncated_files` |
| `pull_request_reviews` | `(pull_request_id, github_id)` | `reviewer_id`, `state`, `submitted_at` |
| `issues` | `(repository_id, number)` | `title`, `state`, `author_id`, `created_at`, `updated_at`, `closed_at`, `labels` (JSONB), `reopened_count` |
| `file_changes` | `(pull_request_id, path)` | `additions`, `deletions`, `is_generated`; `commit_id` nullable and unfilled in Phase 2 |
| `commits` | `(repository_id, sha)` | `author_id` (nullable), `author_name`, `author_email`, `committed_at`, `additions`, `deletions`, `is_merge`, `message` |
| `releases` | `(repository_id, tag)` | `name`, `published_at`, `author_id` |
| `ingestion_jobs` | id | `repository_id`, `status`, `started_at`, `finished_at`, `cursor` (JSONB), `error`, `counts` (JSONB), `resume_after` |

JSONB columns (`labels`, `raw_payload`, `cursor`, `counts`) use a type decorator that renders JSONB
on Postgres and plain JSON on SQLite, so the test suite runs against the same schema.

Indexes: `(repository_id, created_at)` on `pull_requests`, `issues`, `commits`;
`(repository_id, updated_at)` on `pull_requests` and `issues` (the incremental-sync window scan);
FK indexes on `pull_request_id`.

Deferred until their phase — **not** created in Phase 2: `ci_runs` (Phase 4), `metrics` (Phase 3),
`pr_features` / `risk_predictions` / `model_versions` (Phases 6–8), `hotspots` / `anomalies`
(post-MVP). Their planned shape, for reference:

| Table (planned) | Key columns |
|---|---|
| `metrics` | `repository_id`, `metric_key`, `window_start`, `window_end`, `value` (p50/p85 stored as separate keys) |
| `pr_features` | `pull_request_id`, `feature_version`, `as_of` (= PR `created_at`), feature columns / JSONB |
| `risk_predictions` | `pull_request_id`, `model_version_id`, `score`, `tier`, `shap` (JSONB: feature → signed contribution), `scored_at` |
| `ci_runs` | `repository_id`, `workflow`, `branch`, `conclusion`, `started_at`, `completed_at` |
| `hotspots` | `repository_id`, `path`, `score`, `computed_at` |
| `anomalies` | `repository_id`, `metric_key`, `window`, `expected`, `observed`, `method` |
| `model_versions` | `name`, `version`, `dataset_version`, `metrics` (JSONB), `artifact_path`, `is_production` |

Migration/model drift is guarded by `backend/tests/test_migrations.py`, which round-trips
`alembic upgrade head` → `downgrade base` on a scratch Postgres database. `users` is deferred with
OAuth ([product.md §4.2](product.md#42-non-goals-for-v1)).

Columns added beyond the blueprint's original list, and why: `github_id` on contributors (identity
keying), `author_name`/`author_email` on commits (ghost users are unclaimable otherwise),
`truncated_files` ([ADR-006](decisions/ADR-006-history-depth-cap.md)), `updated_at` (incremental
sync), `labels` JSONB and `raw_payload` on PRs.

## 5. Ingestion design

Input: `owner/repository` (public, from an allow-list in v1). Implemented in
`backend/app/ingestion/` ([ADR-008](decisions/ADR-008-graphql-ingestion-strategy.md),
[ADR-009](decisions/ADR-009-ingestion-idempotency-and-resume.md)).

### Phases (in dependency order)

```text
repository → pull_requests → issues → commits → releases → done
```

1. **repository** — `defaultBranchRef.name` and `pullRequests.totalCount`. Above 50 000 PRs the
   window shrinks from 24 to 12 months and the reduction is recorded on the job
   ([ADR-006](decisions/ADR-006-history-depth-cap.md)).
2. **pull_requests** — pages of 100, `orderBy: UPDATED_AT DESC`, with reviews and files nested in
   the same query (one call per page, not 201). A PR whose file connection exceeds the nested
   100-item cap gets follow-up queries up to `INGESTION_MAX_FILE_CHANGES_PER_PR` (1000), then
   `truncated_files = true`. `PENDING` reviews are skipped — requested reviewers, not submitted
   reviews.
3. **issues** — pages of 100, same stop rule, plus labels and a `REOPENED_EVENT` timeline count.
4. **commits** — `ref(qualifiedName: defaultBranch).target.history(first:, since:, until:)`; the
   window is enforced **server-side** because `Commit.history` is the one connection that takes a
   time filter. Skipped entirely when the repository has no default branch.
5. **releases** — REST `/releases`, pages of 100, keeping only rows with `published_at`.
6. **finalize** — `repositories.last_synced_at = now`, job `succeeded`.

### Incremental sync without `since`

`Repository.pullRequests` and `Repository.issues` accept **no `since` argument** (verified against
the published schema), so PRs and issues page `UPDATED_AT DESC` and stop paging when the oldest item
on a page predates `max(window_start, last_synced_at)`. The page that straddles that boundary **is**
stored — dropping it would lose items updated inside the window. Commits filter server-side. This is
the subject of [ADR-008](decisions/ADR-008-graphql-ingestion-strategy.md).

### Rate limits, pausing, and resume

The budget is read from `rateLimit { remaining resetAt }` on every GraphQL response and from the
`x-ratelimit-*` headers on REST. When fewer than `INGESTION_MIN_RATE_BUDGET` points remain the client
raises *before* hitting zero; the runner sets `status = "paused"` with `resume_after` = GitHub's
reset time and leaves the cursor in place. The cursor is persisted **after every page**, so resume
restarts at the next page and a crash costs at most one page.

### Idempotency

Every write is a natural-key upsert (`bulk_upsert`): `INSERT ... ON CONFLICT DO UPDATE` on Postgres,
and a load-then-merge that preserves row ids on SQLite. Re-ingesting the same pages updates rows in
place — never duplicates, never resets progress.

### Cleaning (data-ethics invariant 2: flag, never delete)

- **Bots** — `is_bot` from the GraphQL `isBot` field, or from an explicit, auditable login list in
  `app/ingestion/cleaning.py` (`[bot]` suffix plus `dependabot`, `renovate`, `github-actions`,
  `pre-commit-ci`, `mergify`, `imgbot`, `greenkeeper`, …).
- **Generated files** — `is_generated` from an explicit path-rule list (lockfiles, `dist/`, `build/`,
  `vendor/`, `node_modules/`, `*.min.js`, `*.min.css`, `coverage/`, `*.generated.*`,
  `__snapshots__/`).
- **Ghost users** — `author: null` becomes a placeholder contributor with
  `github_id = "GHOST"` and `is_ghost = true`; commits keep `author_name`/`author_email`, which the
  git payload preserves after the account is gone
  ([ADR-010](decisions/ADR-010-contributor-identity-and-ghosts.md)).

### Label inputs (for Phase 6)

`labels` (JSONB) and `raw_payload` are stored on PRs so the label rules in
[`ml.md` §2](ml.md#2-label-definition) — revert references, `fixes #n` links — can be extracted
later without a re-fetch.

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
