# DevPulse — Portfolio presentation notes

How this project is presented to recruiters and reviewers. Core principle:
**claims must match what is built** ([product.md §4.2](product.md#42-non-goals-for-v1): never
claim ML results that were not measured).

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

## Competitive context

Existing engineering-analytics tools (LinearB, Swarmia, Jellyfish) cover delivery metrics, and
CodeScene popularized behavioral code analysis and hotspots. **Verify their current features before
comparing in the README** — this check happens when the README is finalized, not from memory.

DevPulse's intended differentiation: an **open, transparent, explainable** PR-risk approach — a rule
baseline, honest model comparison, and per-prediction explanations — packaged as a
self-contained, free-to-run project.

## Positioning with NusaFlow

```text
NusaFlow  — Supply Chain Intelligence
  "What is happening in the supply chain, and what should we do?"

DevPulse  — Software Engineering Intelligence
  "What is happening in the software team, what may go wrong,
   why does the system think so, and what should we investigate?"
```

Shared pattern: Real-world problem → Data → Processing → Analytics → ML → Decision engine →
Dashboard → Deployment → Monitoring.

## Demo mode as a portfolio feature

`[ Try Live Demo ]` is the first thing a reviewer interacts with. Requirements:

- Loads with **no login and no ingestion wait** — pre-computed data
  ([ADR-003](decisions/ADR-003-demo-repository.md)).
- Handles a cold-starting backend gracefully (skeleton UI + "waking up the server" message).
- Every number on screen is **real computed data** from `fastapi/fastapi`; placeholder numbers in
  any screenshot or doc are labeled as examples.
