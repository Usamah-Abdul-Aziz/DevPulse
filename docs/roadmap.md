# DevPulse — Roadmap

MVP = **Phases 0–8**, delivered as a deployed, demoable product. UI and deployment are *not* later
phases: each phase ships its slice of UI and is deployed (Phase 1 sets up the deploy pipeline).
Hotspots, anomaly detection, delay prediction, recommendations, observability/MLOps-lite, and
advanced architecture are post-MVP.

```text
GitHub repo → async ingestion → metrics → health score
→ rule-based risk baseline → labeled dataset (as-of features)
→ model comparison + calibration → SHAP + batch scoring
→ PR detail + dashboard → deployed demo
```

## MVP phases

| Phase | Goal | Deliverable | Acceptance criteria | Status |
|---|---|---|---|---|
| **0** Product definition | Fix scope before coding | `README`, `AGENTS.md`, `docs/product.md`, `docs/architecture.md` incl. non-goals | Non-goals, label rules, and MVP defined; open decisions resolved | ✅ Done |
| **1** Foundation + walking skeleton | End-to-end "hello" deployed | Next.js + FastAPI + Postgres + Docker + CI; deployed to Vercel/Render/Supabase | `/docs` and a frontend page live on public URLs; CI runs lint + tests; CORS/env verified | 🚧 In progress — code, tests, Docker, and CI done; external deploy pending |
| **2** Ingestion | GitHub → PostgreSQL | Async ingestion jobs, incremental sync, cleaning | Idempotent re-run; resumes after rate-limit stop; bots and generated files flagged | ✅ Done — [ADR-008](decisions/ADR-008-graphql-ingestion-strategy.md), [009](decisions/ADR-009-ingestion-idempotency-and-resume.md), [010](decisions/ADR-010-contributor-identity-and-ghosts.md) |
| **3** Analytics + demo seed | First dashboard on real data | Metrics (product.md §6), activity dashboard, **pre-ingested demo repo** | Demo loads without ingestion or OAuth; metrics match a manual spot-check of one repo | ☐ |
| **4** Health score | Transparent summary | Health engine + `health_config.yaml` + dashboard | Score reproducible; component breakdown shown; missing-data renormalization works | ☐ |
| **5** Rule-based risk | Baseline to beat | Rules for size/files/review bottleneck; PR list with risk tier | Rules documented; baseline metrics computed on labeled data once available | ☐ |
| **6** ML dataset | Labeled, leakage-free data | Label rules, as-of feature pipeline, `dataset_version` | `test_features_are_as_of` passes; positive rate reported; multi-repo dataset built | ☐ |
| **7** Model training | Choose a model honestly | LR / RF / XGBoost vs. rule baseline; time + cross-repo eval; calibration | Evaluation report with PR-AUC, precision@k, calibration; results measured, not assumed | ☐ |
| **8** Explainability + scoring | Explainable predictions in the product | SHAP, batch scoring job, `risk_predictions`, PR detail page | Every scored PR shows ranked signed factors; scoring runs without live SHAP; model version recorded | ☐ |

## Post-MVP phases

| Phase | Goal | Acceptance criteria |
|---|---|---|
| **9** Code hotspots | Hotspot score + page | Score defined and documented; top files plausible on demo repo |
| **10** Anomaly detection | MAD baseline, optional Isolation Forest | Insufficient-history state handled; bots filtered; method compared |
| **11** Delay prediction | Binary pickup-delay model | Same evaluation protocol as [ml.md §4.2](ml.md#42-evaluation-protocol) |
| **12** Recommendations | Rule / ML / explanation labeled | Each recommendation shows its source label |
| **13** Observability-lite | Know when it breaks | Ingestion status, error log, model version, prediction log visible on a status page |
| **14** MLOps-lite | Reproducibility, not ceremony | `model_versions` + dataset version + evaluation stored; drift report only if data volume justifies it |
| **15** Advanced architecture | Only if needed | Documented reason for each of webhooks / queue / Redis; never added only to enlarge the stack list |

## Phase exit criteria (apply to every phase)

- Acceptance criteria for the phase are met.
- Tests pass (per [`architecture.md` §8](architecture.md#8-testing-and-cicd)).
- Docs updated — the phase's decisions land in `docs/decisions/` as ADRs.
- The deployed slice works (MVP phases).
