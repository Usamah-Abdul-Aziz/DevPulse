# ADR-003: Public demo repository

**Status:** Accepted · **Date:** 2026-10-08 · **Resolves:** Section 25, open decision 3

## Context

Demo Mode (Section 19) is a primary portfolio feature: `[ Try Live Demo ]` must open a
pre-ingested repository with no OAuth and no ingestion wait. The demo repo is the first thing a
reviewer sees, so it must be self-explanatory without inside knowledge.

## Decision

**Primary demo repository: `fastapi/fastapi`.**

**Backup: `pallets/flask`** (kept as a second pre-ingested repo in case FastAPI's data profile
turns out to be uninteresting — e.g. too few risk positives to make the SHAP screen meaningful).

## Rationale

- **Relatable to the stack:** DevPulse's own backend is FastAPI. A reviewer sees the tool analyze
  the very framework the tool is built with — a self-referential, memorable demonstration.
- **Interesting data profile:** large enough (hundreds of contributors, thousands of PRs) for
  real cycle-time variation, review bottlenecks, and a non-trivial health score, but small enough
  to ingest inside free-tier limits.
- **Active and familiar:** high name recognition means the numbers look plausible on inspection
  rather than needing to be taken on faith.
- **Bug labels + revert history exist**, so the demo's risk predictions rest on real labels, not
  fabrications.

## Consequences

- The demo repo is ingested **once, offline**, and its metrics / health / predictions / SHAP are
  **pre-computed into the database** during Phase 3 (per Section 19, demo data is pre-computed in
  Phase 3, not generated on demand).
- The demo dataset is rebuilt by a script, not hand-edited — demo numbers must always be real
  computed data (Section 19).
- The demo is served from the same read API as everything else; `/api/v1/demo` simply points at
  the repository row where `is_demo = true`.
- History depth for the demo follows ADR-006 (24 months), so the trends screens have enough
  series to plot.
