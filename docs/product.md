# DevPulse — Product Specification

> **DevPulse analyzes software-development activity from GitHub and uses analytics + machine
> learning to surface project health, delivery risks, code hotspots, and engineering bottlenecks
> — with explanations a tech lead can act on.**

This document defines *what* DevPulse is and what it does. For *how* it is built, see
[`architecture.md`](architecture.md); for the ML system, [`ml.md`](ml.md); for the schedule,
[`roadmap.md`](roadmap.md).

---

## 1. Vision

DevPulse is not a GitHub dashboard. It is a **decision-support platform** that answers:

> *"What is happening in this software project, what is likely to go wrong, why does the system
> think so, and what should the engineering team investigate?"*

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

## 2. Problem

Raw Git activity does not answer the questions engineering leads actually ask:

- Is the project healthy, and is delivery getting slower?
- Which open Pull Requests are risky, and why?
- Are reviews becoming a bottleneck?
- Is knowledge or workload overly concentrated?
- Are there unusual development patterns?
- Which areas should we investigate first?

## 3. Users and primary scenario

**Primary user:** Engineering Managers and Tech Leads.
**Secondary audience:** recruiters and reviewers evaluating this as a portfolio project (served by
Demo Mode, [§8](#8-demo-mode)).

**Primary scenario — "Monday triage":** a tech lead opens DevPulse, sees the repo's health at a
glance, sees which open PRs are high-risk and why, sees whether review time is degrading, and
leaves with 2–3 concrete things to look at. **Every dashboard screen is judged against this
scenario.**

Potential later users: software engineers, CTOs, project managers, DevOps engineers.

## 4. Scope

### 4.1 v1 goals

- Ingest one or more **public GitHub repositories**.
- Compute engineering metrics and a transparent Project Health Score.
- Predict PR risk at PR-open time with an explainable model, compared against a rule-based
  baseline.
- Provide a deployed dashboard with a pre-ingested demo.

### 4.2 Non-goals for v1

- **GitLab support** (kept as future work).
- **Private repositories and GitHub OAuth login.** v1 uses a server-side read-only token and a
  repository allow-list; `users` and `/login` are deferred.
- Real-time ingestion (webhooks, queues, Kafka).
- Ranking or scoring individual developers. Contributor views show distribution/concentration
  signals only.
- Multi-tenancy, billing, enterprise SSO.
- Claiming ML results that were not measured.

## 5. Feature map

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

## 6. Engineering metrics

### 6.1 Conventions (apply to all metrics)

- Use **median and percentiles (p50 / p85)** for durations. Means are skewed by outliers.
- Exclude **bots** (e.g. Dependabot, Renovate, `*[bot]` accounts) from contributor and workload
  metrics; flag them with `is_bot` in the data model.
- Exclude **generated and vendored files** (lockfiles, `dist/`, `vendor/`, `*.min.js`, snapshots)
  from churn and PR size.
- Exclude **draft time** from review metrics where the API provides the data.
- Squash-merge repos change commit-level metrics; prefer PR-level metrics where possible.
- Metrics are computed per repository and per time window (week by default).

### 6.2 PR cycle time, decomposed

```text
Cycle time    = merged_at - created_at
  ├── Pickup time   = first_review_at - created_at
  ├── Review time   = approved_at - first_review_at
  └── Merge delay   = merged_at - approved_at
```

Report p50 and p85 per week, plus the breakdown, so a lead can tell *where* time is lost.

### 6.3 Metric catalog

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

### 6.4 DORA alignment

| DORA metric | DevPulse proxy |
|---|---|
| Lead time for changes | PR cycle time (first commit → merge when data allows) |
| Deployment frequency | Release / tag frequency |
| Change failure rate | Share of merged PRs later labeled risky ([`ml.md` §2](ml.md)) |
| Time to restore | Out of scope for v1 |

Name these as *proxies derived from repository data*, not as official DORA measurements.

## 7. Project Health Score

The central summary of DevPulse. It is **rule-based, transparent, and configurable** — not ML.

### 7.1 Components and default weights

```text
Health Score (0–100)
├── Delivery Velocity     20%
├── PR Health             20%
├── Code Stability        20%
├── Contributor Balance   15%
├── Issue Health          15%
└── CI/CD Stability       10%
```

If a component has no data (e.g. no CI), exclude it and **renormalize** the remaining weights.
Show which components were excluded.

### 7.2 Sub-score definitions

| Component | Inputs (examples) |
|---|---|
| Delivery Velocity | Trend in merged PRs per week vs. trailing baseline; release frequency |
| PR Health | p85 cycle time, p85 pickup time, share of XL PRs |
| Code Stability | Churn on recently modified files, revert/rework rate |
| Contributor Balance | Concentration of merged PRs / commits (top-contributor share, entropy) |
| Issue Health | Issue resolution p85, reopen rate, backlog growth |
| CI/CD Stability | Default-branch success rate, flaky-run rate |

### 7.3 Normalization

Each input maps to 0–100 with **linear interpolation between a "good" and a "poor" threshold**,
defined in a versioned config file (`health_config.yaml`). Two modes:

1. **Absolute thresholds** (default) — see [`metrics.md`](metrics.md) for the initial values and
   the validation plan.
2. **Self-baseline** — compare against the repository's own trailing 90-day distribution (useful
   for detecting *change*).

### 7.4 Example (illustrative; recomputed from real data in the app)

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

## 8. Demo mode

- `[ Try Live Demo ]` opens a pre-ingested repository with **no OAuth and no ingestion wait**.
- Demo data is **pre-computed** (metrics, health, predictions, SHAP) and served from the database,
  so the first page does not depend on a cold backend doing heavy work.
- Show skeleton loading states and a friendly "waking up the server" message for cold starts.
- Demo numbers must come from real computed data. If any screenshot or README uses placeholder
  numbers, label them as examples.

The demo repository is `fastapi/fastapi` ([ADR-003](decisions/ADR-003-demo-repository.md)).

## 9. Security and data ethics

- Never commit secrets: GitHub token, database URL, secret keys. Use `.env` and provide
  `.env.example`.
- Use a read-only token; respect GitHub's API terms and rate limits.
- Only public repositories in v1; show the source repository clearly.
- **Individual-level data:** default views are aggregated; no leaderboards, no "developer
  performance" scores. Contributor concentration is a team risk signal.
- Document label noise and model limitations wherever predictions are shown.

## 10. Post-MVP intelligence features

See [`ml.md`](ml.md) §5: code hotspots, anomaly detection, delivery delay prediction, and the
recommendation engine.
