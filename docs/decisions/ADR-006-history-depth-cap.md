# ADR-006: History depth cap per repository

**Status:** Accepted · **Date:** 2026-10-08 · **Resolves:** Section 25, open decision 6

## Context

Section 13.5 caps history depth "to stay within free-tier limits", but does not state the number.
Deeper history means better features and more training rows; it also means a much larger
ingestion bill against GitHub rate limits and a bigger database.

## Decision

- **Training repositories: 24 months** of history (items with `created_at` within the trailing 24
  months at extraction time).
- **Demo repository (`fastapi/fastapi`): 24 months** as well, so demo trends have a long enough
  series while the demo stays cheap to load on a cold backend.
- **Hard caps to protect free-tier memory:**
  - repositories with more than **~50 000 PRs / 24 months** are ingested with a reduced window
    (12 months) and the reduction is recorded in `ingestion_jobs`;
  - `file_changes` rows are capped per PR at **1000 files** (beyond that, store the first 1000 and
    set a `truncated_files` flag — vendored bulk updates dominate and add no analytic value).

## Rationale

- 24 months covers two full years of weekly series — enough for trend, seasonality-by-eye, and the
  ≥ 26-week minimum history the anomaly detector needs (Section 9.2), without paying for a
  project's entire history.
- 12 months is the fallback for the few very-large repos (e.g. `rust-lang/rust`, `pandas`) where
  24 months would blow the budget; the reduction is explicit, never silent.
- The 1000-file cap targets generated/vendored mega-PRs specifically; they are already filtered
  from churn metrics, so storing every row is pure cost.

## Consequences

- The window is stored **per dataset version** (`dataset_version` records the extraction date and
  the window), so a re-extraction with a different window is a new version.
- Feature windows are nested inside the cap: `file_prior_*_90d` / `_180d` features always fit
  inside 24 months of history.
- The cap makes the demo's cold-start fast: the demo repo's pre-computed pages never scan more
  than 24 months of rows.
