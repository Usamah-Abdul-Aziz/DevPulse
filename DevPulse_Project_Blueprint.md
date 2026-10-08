# DevPulse — Blueprint v2

> **DevPulse analyzes software-development activity from GitHub and uses analytics + machine learning to surface project health, delivery risks, code hotspots, and engineering bottlenecks — with explanations a tech lead can act on.**

**Status:** planning · **Version:** 2 (revised after blueprint review)

This single file contains the product spec, technical design, roadmap, and portfolio notes. When the repo is created, split it into `docs/product.md`, `docs/architecture.md`, `docs/ml.md`, `docs/roadmap.md`, and `docs/portfolio.md`, and keep `AGENTS.md` for the agent guidance in Section 24.

## Changes from v1

| Area | Change |
|---|---|
| MVP | Single, unambiguous definition (Section 17). Dashboard and deployment are delivered incrementally inside Phases 1–8, not deferred to Phases 12–13. |
| ML | Prediction time fixed at **PR open**; features are *as-of* only; label rules defined; time-based and cross-repo splits; calibration; honest baseline comparison. |
| SHAP | Presented as signed contributions, not additive percentages. |
| Health score | One six-component definition, explicit normalization, consistent example. |
| Ingestion | Asynchronous jobs, rate-limit strategy, bot/generated-file filtering. GitLab and OAuth are non-goals for v1. |
| Demo | Pre-computed demo snapshot built in Phase 3, not at the end. |
| Deployment | Walking-skeleton deploy in Phase 1; ML inference is batch, not live. |
| Doc | Added non-goals, acceptance criteria per phase, risks, open decisions. Removed duplicated examples. |

---

# 1. Vision

DevPulse is not a GitHub dashboard. It is a **decision-support platform** that answers:

> *"What is happening in this software project, what is likely to go wrong, why does the system think so, and what should the engineering team investigate?"*

```text
GitHub (public repos)
   ├── Commits, Pull Requests, Reviews
   ├── Issues, Contributors
   ├── Files changed
   └── CI runs (GitHub Actions / check runs)
          │
          ▼
   Async ingestion jobs → PostgreSQL (raw + normalized)
          │
          ▼
   Feature engineering (as-of snapshots)
       ┌───┴───┐
       ▼       ▼
  Analytics    ML (offline training, batch scoring)
       └───┬───┘
           ▼
   FastAPI → Next.js dashboard
```

# 2. Problem

Raw Git activity does not answer the questions engineering leads actually ask:

- Is the project healthy, and is delivery getting slower?
- Which open Pull Requests are risky, and why?
- Are reviews becoming a bottleneck?
- Is knowledge or workload overly concentrated?
- Are there unusual development patterns?
- Which areas should we investigate first?

# 3. Users and Primary Scenario

**Primary user:** Engineering Managers and Tech Leads.
**Secondary audience:** recruiters and reviewers evaluating this as a portfolio project (served by Demo Mode, Section 19).

**Primary scenario — "Monday triage":** a tech lead opens DevPulse, sees the repo's health at a glance, sees which open PRs are high-risk and why, sees whether review time is degrading, and leaves with 2–3 concrete things to look at. Every dashboard screen should be judged against this scenario.

Potential later users: software engineers, CTOs, project managers, DevOps engineers.

# 4. Scope

## 4.1 v1 goals

- Ingest one or more **public GitHub repositories**.
- Compute engineering metrics and a transparent Project Health Score.
- Predict PR risk at PR-open time with an explainable model, compared against a rule-based baseline.
- Provide a deployed dashboard with a pre-ingested demo.

## 4.2 Non-goals for v1

- **GitLab support** (kept as future work).
- **Private repositories and GitHub OAuth login.** v1 uses a server-side read-only token and a repository allow-list; `users` and `/login` are deferred.
- Real-time ingestion (webhooks, queues, Kafka).
- Ranking or scoring individual developers. Contributor views show distribution/concentration signals only.
- Multi-tenancy, billing, enterprise SSO.
- Claiming ML results that were not measured.

# 5. Feature Map

| Feature | MVP | Later |
|---|:--:|:--:|
| Repository ingestion (async, public repos) | ✓ | |
| Engineering metrics | ✓ | |
| Project Health Score (rule-based) | ✓ | |
| Rule-based PR risk baseline | ✓ | |
| ML PR risk (XGBoost) + SHAP | ✓ | |
| Pre-computed demo repository | ✓ | |
| Code hotspots | | ✓ |
| Anomaly detection | | ✓ |
| Delivery delay prediction | | ✓ |
| Recommendation engine | | ✓ |
| Observability / MLOps-lite | | ✓ |
| Webhooks, queue, Redis | | ✓ (only if justified) |

---

# 6. Engineering Metrics

## 6.1 Conventions (apply to all metrics)

- Use **median and percentiles (p50 / p85)** for durations. Means are skewed by outliers.
- Exclude **bots** (e.g. Dependabot, Renovate, `*[bot]` accounts) from contributor and workload metrics; flag them with `is_bot` in the data model.
- Exclude **generated and vendored files** (lockfiles, `dist/`, `vendor/`, `*.min.js`, snapshots) from churn and PR size.
- Exclude **draft time** from review metrics where the API provides the data.
- Squash-merge repos change commit-level metrics; prefer PR-level metrics where possible.
- Metrics are computed per repository and per time window (week by default).

## 6.2 PR cycle time, decomposed

```text
Cycle time    = merged_at - created_at
  ├── Pickup time   = first_review_at - created_at
  ├── Review time   = approved_at - first_review_at
  └── Merge delay   = merged_at - approved_at
```

Report p50 and p85 per week, plus the breakdown, so a lead can tell *where* time is lost.

## 6.3 Metric catalog

| Metric | Definition | Notes |
|---|---|---|
| Commit frequency | Non-bot commits per week | Context only; high is not automatically good |
| PR cycle time | See 6.2 | p50 / p85 |
| Pickup time | Created → first review | Key bottleneck signal |
| Code churn | Lines added + deleted (filtered) | By directory/module |
| PR size | Lines changed (filtered) and files changed | Bucketed: S / M / L / XL |
| Contributor distribution | Share of merged PRs and commits per contributor | Presented as concentration, never as performance |
| Issue resolution time | Opened → closed (p50 / p85) | |
| Reopened issues | Count and rate | |
| CI success rate | Successful / total runs on default branch | Where CI data exists |
| Release frequency | Releases/tags per period | Where available |

## 6.4 DORA alignment

| DORA metric | DevPulse proxy |
|---|---|
| Lead time for changes | PR cycle time (first commit → merge when data allows) |
| Deployment frequency | Release / tag frequency |
| Change failure rate | Share of merged PRs later labeled risky (Section 8.2) |
| Time to restore | Out of scope for v1 |

Name these as *proxies derived from repository data*, not as official DORA measurements.

---

# 7. Project Health Score

The central summary of DevPulse. It is **rule-based, transparent, and configurable** — not ML.

## 7.1 Components and default weights

```text
Health Score (0–100)
├── Delivery Velocity     20%
├── PR Health             20%
├── Code Stability        20%
├── Contributor Balance   15%
├── Issue Health          15%
└── CI/CD Stability       10%
```

If a component has no data (e.g. no CI), exclude it and **renormalize** the remaining weights. Show which components were excluded.

## 7.2 Sub-score definitions

| Component | Inputs (examples) |
|---|---|
| Delivery Velocity | Trend in merged PRs per week vs. trailing baseline; release frequency |
| PR Health | p85 cycle time, p85 pickup time, share of XL PRs |
| Code Stability | Churn on recently modified files, revert/rework rate |
| Contributor Balance | Concentration of merged PRs / commits (e.g. top-contributor share, entropy) |
| Issue Health | Issue resolution p85, reopen rate, backlog growth |
| CI/CD Stability | Default-branch success rate, flaky-run rate |

## 7.3 Normalization

Each input maps to 0–100 with **linear interpolation between a "good" and a "poor" threshold**, defined in a versioned config file (`health_config.yaml`). Two modes:

1. **Absolute thresholds** (default) — e.g. pickup p85: ≤ 4h → 100, ≥ 72h → 0.
2. **Self-baseline** — compare against the repository's own trailing 90-day distribution (useful for detecting *change*).

Thresholds are starting points; validate them on several repositories whose condition is known to you and adjust. Document the final values in `docs/ml.md` or `docs/metrics.md`.

## 7.4 Example (illustrative; recomputed from real data in the app)

```text
Delivery Velocity      82
PR Health              76
Code Stability         89
Contributor Balance    72
Issue Health           80
CI/CD Stability        91
───────────────────────
Overall                81   (0.20·82 + 0.20·76 + 0.20·89 + 0.15·72 + 0.15·80 + 0.10·91)
```

Bands: 80–100 Healthy · 60–79 Watch · < 60 At risk (configurable).

---

# 8. PR Risk Prediction (core ML)

## 8.1 Problem statement

> At the moment a PR is **opened**, estimate the likelihood that it will cause rework or regression after merge, and explain the main contributing factors.

**Prediction time is PR open.** Only information available at that moment may be used as a feature. Review-derived signals (review count, review delay, cycle time) are known only later; they are shown in the UI as *observed signals*, not model inputs. (A second, post-review model is optional future work.)

## 8.2 Label definition

```text
high_risk = 1  if, within 14 days after merge, at least one holds:
  (a) a revert commit/PR references this PR or its merge commit
  (b) a follow-up PR that touches ≥1 of the same files, merged within 14 days,
      and is linked to a bug issue (label `bug`) or carries a fix keyword
      (fix, hotfix, regression) in title/branch
high_risk = 0  otherwise (only for PRs old enough that the 14-day window has closed)
```

Rules:

- Document the heuristic precisely in `docs/ml.md`; it is a SZZ-lite approximation and **label noise is expected**.
- Report the positive rate per repository. If positives are too few (set a minimum, e.g. < 30 per training repo), exclude the repo or pool it.
- Do not describe labels as developer quality or blame.
- Unmerged and still-open PRs are scored, but never used as labeled training rows.

## 8.3 Features (all computed *as-of* PR creation time)

| Group | Features |
|---|---|
| Size | `lines_added`, `lines_deleted`, `files_changed`, `dirs_touched` (filtered for generated files) |
| File history | `file_prior_change_count_90d`, `file_prior_churn_90d`, `file_prior_bugfix_count_180d` (max / mean across touched files) |
| Author history | `author_prior_merged_prs`, `author_prior_risk_rate` (labeled history before this PR only), `author_familiarity_with_files` |
| Context | `day_of_week`, `hour_opened`, `is_draft_at_open`, `has_tests_changed`, `has_linked_issue` |

`file_hotspot_score` (the Phase 9 composite) is **not** an MVP feature; the file-history features above are its raw ingredients.

**Leakage rule:** every historical aggregate must be computed from data with timestamp < PR `created_at`. Add an automated test (`test_features_are_as_of`) that recomputes features at a past cut-off and asserts no later data was used.

## 8.4 Dataset

- Train on **multiple public repositories** (target 10–30 active repos with enough PR volume, a mix of sizes and languages), not on one repo. Record selection criteria in `docs/ml.md`.
- Store a versioned dataset snapshot (`dataset_version`) with extraction date and label rules.

## 8.5 Evaluation protocol

- **Time-based split:** train on earlier PRs, validate/test on later PRs. No random split.
- **Cross-repo check:** hold out whole repositories to estimate generalization.
- **Models, in order:** (1) rule-based baseline from Phase 5, (2) Logistic Regression, (3) Random Forest, (4) XGBoost.
- **Metrics:** PR-AUC (primary, for imbalance), ROC-AUC, precision/recall at the chosen threshold, **precision@k / recall@k** for the top-k riskiest PRs (matches how a lead uses it), Brier score and calibration curve.
- Report the **positive rate** next to every metric.
- Report honestly if XGBoost is only marginally better than the rule baseline. That is a valid, credible result.
- Never publish metric numbers that were not measured; example numbers in docs are placeholders and must be marked as such.

## 8.6 Probability and risk tiers

XGBoost scores with class weighting are usually **not calibrated probabilities**. Calibrate (isotonic or Platt) on a validation slice, check the calibration curve, and then either show the calibrated probability or show **risk tiers** (HIGH / MEDIUM / LOW) derived from percentiles or thresholds. Avoid wording like "78% chance of regression" unless calibration supports it.

## 8.7 Explainability (SHAP)

For tree models, SHAP values are additive in **log-odds**, not in percentage points. Therefore:

```text
PR #182 — Risk: HIGH (calibrated score 0.78)

Top contributing factors (↑ raises risk, ↓ lowers risk)
↑↑↑  Files changed: 18                 (strongest)
↑↑   Prior churn in touched files
↑↑   Touches files with prior bug fixes
↑    Large PR size (+1,284 / -321)
↓    Author has high familiarity with these files
```

Show a ranked, signed contribution bar chart. Do **not** present SHAP values as "+24%, +21%, … = 91%".

SHAP is computed **in batch at scoring time** and stored (Section 12), not calculated live per request.

---

# 9. Post-MVP Intelligence Features

## 9.1 Code Hotspots (Phase 9)

```text
Hotspot Score (0–100) = normalized( change_frequency × code_churn ,
                                    with recency decay )
                        combined with historical bug-fix touches
```

- Computed per file from `file_changes`, with time decay (recent changes matter more).
- Optional: complexity metrics where cheaply available.
- A hotspot means "deserves attention", not "bad code". Display as a **score**, not a probability.

## 9.2 Anomaly Detection (Phase 10)

- Start with a **robust z-score / MAD** baseline on weekly series (commits, merged PRs, churn, p85 cycle time).
- Compare with **Isolation Forest** on multi-feature weekly vectors; keep it only if it adds value.
- Require sufficient history (e.g. ≥ 26 weeks) per repo before alerting; otherwise show "insufficient data".
- Bots and generated files are filtered before computing features.
- An anomaly is a signal to investigate, **not** evidence of a problem or wrongdoing.

## 9.3 Delivery Delay Prediction (Phase 11)

- Target: **binary** — pickup time (or cycle time) greater than the repository's own p75 — instead of the 3-class output in v1.
- Features known at PR open: size, files changed, number of requested reviewers, day/time opened, historical pickup time of the touched area.
- Evaluate with the same protocol as Section 8.5.

## 9.4 Recommendation Engine (Phase 12)

Recommendations combine three clearly labeled sources:

| Source label | Example |
|---|---|
| **Rule** | "PR touches > 15 files — consider splitting." |
| **ML signal** | "Model flags this PR as high risk; top factor: prior bug fixes in touched files." |
| **Explanation** | Plain-language reason built from SHAP / rule inputs. |

```text
HIGH PR RISK — PR #182

Recommended actions
1. Split the PR into smaller changes                      [Rule]
2. Add a reviewer familiar with payment/service.py        [Rule]
3. Review payment/service.py carefully                    [ML signal]
4. Confirm test coverage for the retry path               [Rule]
```

---

# 10. System Architecture

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

Key decisions:

- **Training is offline** (notebooks / scripts in `ml/`). The backend only loads a versioned model artifact for **batch scoring**; predictions and SHAP values are stored in the database and served as plain reads.
- **Ingestion is asynchronous from day one** (job table + FastAPI background tasks). A lightweight queue (RQ/Celery + Redis) is introduced only if background tasks prove insufficient.
- Free-tier hosts have small memory; do not run SHAP or model training inside a request.

# 11. Tech Stack

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

# 12. Data Model

Initial entities (all repo-scoped tables carry `repository_id`):

| Table | Key columns / constraints |
|---|---|
| `repositories` | `owner`, `name` (unique together), `default_branch`, `last_synced_at`, `is_demo` |
| `contributors` | `repository_id`, `login`, `is_bot`, merged identities (email/login aliases) |
| `commits` | `sha` (unique per repo), `author_id`, `committed_at`, additions, deletions, `is_merge` |
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

Also: store the raw GitHub payload (JSONB) for PRs so re-extraction does not require re-fetching; add indexes on (`repository_id`, `created_at`) for time-series queries. `users` is deferred with OAuth (Section 4.2).

# 13. Ingestion Design

Input: `owner/repository` (public, from an allow-list in v1).

1. **API strategy:** prefer the GraphQL API for PRs + reviews + files in fewer calls; use REST for CI runs and releases. Avoid N+1 requests per PR.
2. **Rate limits:** read rate-limit headers, back off with jitter, and stop the job cleanly when the budget is exhausted (resume from a stored cursor).
3. **Incremental sync:** after the first full sync, fetch only items updated since `last_synced_at` (cursor / `since` / ETag).
4. **Jobs:** `POST /connect` creates an `ingestion_jobs` row and returns immediately; the UI polls job status.
5. **Size limits:** cap history depth (e.g. last 12–24 months) and repository size for the demo to stay within free-tier limits.
6. **Cleaning:** flag bots, mark generated files, merge author identities, handle deleted ("ghost") users.
7. **Label inputs:** also fetch revert references, issue links (`fixes #n`), and issue labels needed by Section 8.2.

**Acceptance:** a medium public repository can be ingested end-to-end, re-run idempotently, and resumed after a simulated rate-limit stop.

# 14. API Design

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

All list endpoints are paginated; hotspots and anomalies are repository-scoped (consistent with the frontend routes).

# 15. Frontend Routes

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

`/login` is deferred (Section 4.2). Prioritize clarity over visual complexity; validate each screen against the Monday-triage scenario.

# 16. Repository Structure

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

Boundary: `ml/` trains and evaluates; `backend/app/ml/` only loads a versioned artifact and scores. Feature code shared by both lives in one package imported by both, so training and serving cannot drift apart.

---

# 17. Roadmap and MVP

## 17.1 MVP definition

**MVP = Phases 0–8, delivered as a deployed, demoable product.** UI and deployment are *not* later phases; each phase ships its slice of UI and is deployed (Phase 1 sets up the deploy pipeline). Hotspots, anomaly detection, delay prediction, recommendations, observability/MLOps-lite, and advanced architecture are post-MVP.

```text
GitHub repo → async ingestion → metrics → health score
→ rule-based risk baseline → labeled dataset (as-of features)
→ model comparison + calibration → SHAP + batch scoring
→ PR detail + dashboard → deployed demo
```

## 17.2 Phases and acceptance criteria

| Phase | Goal | Deliverable | Acceptance criteria |
|---|---|---|---|
| **0** Product definition | Fix scope before coding | `README`, `AGENTS.md`, `docs/product.md`, `docs/architecture.md` incl. non-goals | Non-goals, label rules, and MVP defined; open decisions (Section 25) resolved |
| **1** Foundation + walking skeleton | End-to-end "hello" deployed | Next.js + FastAPI + Postgres + Docker + CI; deployed to Vercel/Render/Supabase | `/docs` and a frontend page live on public URLs; CI runs lint + tests; CORS/env verified |
| **2** Ingestion | GitHub → PostgreSQL | Async ingestion jobs, incremental sync, cleaning | Idempotent re-run; resumes after rate-limit stop; bots and generated files flagged |
| **3** Analytics + demo seed | First dashboard on real data | Metrics (Section 6), activity dashboard, **pre-ingested demo repo** | Demo loads without ingestion or OAuth; metrics match a manual spot-check of one repo |
| **4** Health score | Transparent summary | Health engine + `health_config.yaml` + dashboard | Score reproducible; component breakdown shown; missing-data renormalization works |
| **5** Rule-based risk | Baseline to beat | Rules for size/files/review bottleneck; PR list with risk tier | Rules documented; baseline metrics computed on labeled data once available |
| **6** ML dataset | Labeled, leakage-free data | Label rules, as-of feature pipeline, `dataset_version` | `test_features_are_as_of` passes; positive rate reported; multi-repo dataset built |
| **7** Model training | Choose a model honestly | LR / RF / XGBoost vs. rule baseline; time + cross-repo eval; calibration | Evaluation report with PR-AUC, precision@k, calibration; results measured, not assumed |
| **8** Explainability + scoring | Explainable predictions in the product | SHAP, batch scoring job, `risk_predictions`, PR detail page | Every scored PR shows ranked signed factors; scoring runs without live SHAP; model version recorded |

### Post-MVP

| Phase | Goal | Acceptance criteria |
|---|---|---|
| **9** Code hotspots | Hotspot score + page | Score defined and documented; top files plausible on demo repo |
| **10** Anomaly detection | MAD baseline, optional Isolation Forest | Insufficient-history state handled; bots filtered; method compared |
| **11** Delay prediction | Binary pickup-delay model | Same evaluation protocol as Section 8.5 |
| **12** Recommendations | Rule / ML / explanation labeled | Each recommendation shows its source label |
| **13** Observability-lite | Know when it breaks | Ingestion status, error log, model version, prediction log visible on a status page |
| **14** MLOps-lite | Reproducibility, not ceremony | `model_versions` + dataset version + evaluation stored; drift report only if data volume justifies it |
| **15** Advanced architecture | Only if needed | Documented reason for each of webhooks / queue / Redis; never added only to enlarge the stack list |

---

# 18. Testing and CI/CD

**Backend (pytest):** API endpoints, DB operations, metric calculations (with fixed fixtures), ingestion (mocked GitHub), batch scoring.

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

**Pipeline:** Push → Lint → Unit tests → Build → Deploy (separate `backend.yml`, `frontend.yml`, `ml.yml`).

# 19. Deployment and Demo Mode

```text
Frontend → Vercel Hobby
Backend  → Render Free
Database → Supabase Free
```

Target: **Rp0 for development and the portfolio demo**, within free-tier limits. Before promising this publicly, **verify the current limits** of Render, Vercel, Supabase, and GitHub Actions (free tiers change). Points to check specifically: backend sleep/cold start on Render Free, database inactivity pausing and storage limits on Supabase Free, and memory limits for the backend instance.

## Demo Mode (a major portfolio feature)

- `[ Try Live Demo ]` opens a pre-ingested repository with **no OAuth and no ingestion wait**.
- Demo data is **pre-computed** (metrics, health, predictions, SHAP) and served from the database or a static snapshot, so the first page does not depend on a cold backend doing heavy work.
- Show skeleton loading states and a friendly "waking up the server" message for cold starts.
- Demo numbers must come from real computed data. If any screenshot or README uses placeholder numbers, label them as examples.

# 20. Security and Data Ethics

- Never commit secrets: GitHub token, database URL, secret keys. Use `.env` and provide `.env.example`:

```env
DATABASE_URL=
GITHUB_TOKEN=            # read-only, public-repo scope
SECRET_KEY=
# Deferred until OAuth is added:
# GITHUB_CLIENT_ID=
# GITHUB_CLIENT_SECRET=
```

- Use a read-only token; respect GitHub's API terms and rate limits.
- Only public repositories in v1; show the source repository clearly.
- **Individual-level data:** default views are aggregated; no leaderboards, no "developer performance" scores. Contributor concentration is a team risk signal.
- Document label noise and model limitations wherever predictions are shown.

# 21. Observability (post-MVP, lightweight first)

Track: API logs, ingestion job status and errors, model version used for each prediction, and scoring runs. A simple internal status page (API, database, GitHub API, last ingestion, current model version) is enough. Drift monitoring is justified only when there is enough ongoing data to make it meaningful.

# 22. Risks and Mitigations

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

# 23. Competitive Context

Existing engineering-analytics tools (e.g. LinearB, Swarmia, Jellyfish) cover delivery metrics, and CodeScene popularized behavioral code analysis and hotspots. Verify their current features before comparing in the README. DevPulse's intended differentiation: an **open, transparent, explainable** PR-risk approach — a rule baseline, honest model comparison, and per-prediction explanations — packaged as a self-contained, free-to-run project.

# 24. Guidance for AI Coding Agents (`AGENTS.md` seed)

- Follow the phase order in Section 17; do not implement post-MVP features during the MVP.
- Do not add infrastructure (Redis, Kafka, queues) without a written reason in `docs/decisions/`.
- Features must be **as-of** PR creation; never use review/merge data as model inputs.
- Never fabricate metric values; evaluation numbers come from reproducible scripts.
- Every phase ends with passing tests, updated docs, and a working deployed slice.
- Keep secrets out of the repo; update `.env.example` when adding config.
- Prefer small, reviewable commits; one acceptance-criteria item per PR where practical.

# 25. Open Decisions (resolve in Phase 0)

- [ ] Final list of 10–30 training repositories and selection criteria
- [ ] Exact label window (14 days proposed) and fix-keyword list
- [ ] Which repository becomes the public demo
- [ ] Health thresholds per metric (initial values and validation repos)
- [ ] Risk tier cut-offs (percentile vs. calibrated-probability thresholds)
- [ ] History depth cap per repository (months)
- [ ] Hosting plan if free-tier limits prove insufficient

---

# 26. Portfolio Presentation

## README structure

```text
# DevPulse
AI-Powered Software Engineering Intelligence Platform
[Live Demo] [Documentation] [Architecture] [API Docs]

## Problem
## Solution
## Architecture
## ML Pipeline        (labels, as-of features, splits)
## Evaluation         (measured PR-AUC, precision@k, calibration — real numbers only)
## Features
## Tech Stack
## Deployment
## Limitations        (label noise, public repos only, free-tier constraints)
## Future Work
```

## Claims should match what is built

| Skill area | Claim only when built |
|---|---|
| Software engineering | TypeScript, Next.js, FastAPI, REST, PostgreSQL, SQLAlchemy, Docker — **MVP** |
| Data engineering | Ingestion, ETL, feature engineering, historical aggregation — **MVP** |
| Machine learning | Supervised learning, XGBoost, calibration, imbalanced classification, SHAP — **MVP**; Isolation Forest — **post-MVP** |
| DevOps | GitHub Actions, Vercel, Render, Supabase — **MVP** |
| System design | Async job processing — **MVP**; caching, queues, webhooks — only if Phase 15 is done |
| MLOps | Model versioning and evaluation tracking — **post-MVP (lightweight)**; drift monitoring — only if implemented |

## Positioning with NusaFlow

```text
NusaFlow  — Supply Chain Intelligence
  "What is happening in the supply chain, and what should we do?"

DevPulse  — Software Engineering Intelligence
  "What is happening in the software team, what may go wrong,
   why does the system think so, and what should we investigate?"
```

Shared pattern: Real-world problem → Data → Processing → Analytics → ML → Decision engine → Dashboard → Deployment → Monitoring.