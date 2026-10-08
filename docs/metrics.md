# DevPulse — Metrics and Health Score reference

This document is the reference for engineering-metric definitions and the Project Health Score
configuration. Metric *semantics* are defined in [`product.md` §6](product.md#6-engineering-metrics);
this file holds the **numeric thresholds** and their validation status.

---

## 1. Health score composition

```text
Health Score (0–100)
├── Delivery Velocity     20%
├── PR Health             20%
├── Code Stability        20%
├── Contributor Balance   15%
├── Issue Health          15%
└── CI/CD Stability       10%
```

- Component scores are linearly interpolated between the **good** (→ 100) and **poor** (→ 0)
  thresholds below, then clamped to [0, 100], then weight-averaged.
- A component with **no data** is excluded and the remaining weights are **renormalized**; the
  excluded components are listed in the UI next to the score.
- Bands: **80–100 Healthy · 60–79 Watch · < 60 At risk** (configurable).

## 2. Threshold values (initial, UNVALIDATED)

> **Status: these are starting points, not calibrated values.** They are validated on real
> repositories during Phase 4 per [ADR-004](decisions/ADR-004-health-thresholds.md); this section
> is updated when that validation lands, and each threshold records its validation status.

| Component | Input | Good (→ 100) | Poor (→ 0) | Validated? |
|---|---|---|---|---|
| Delivery Velocity | merged PRs/week, trend vs trailing 90d | ≥ 1.25× baseline | ≤ 0.70× baseline | ✗ |
| | releases per 90 days | ≥ 4 | 0 | ✗ |
| PR Health | pickup time p85 | ≤ 4 h | ≥ 72 h | ✗ |
| | cycle time p85 | ≤ 24 h | ≥ 168 h (7 d) | ✗ |
| | share of XL PRs (> 1000 lines changed) | ≤ 5 % | ≥ 30 % | ✗ |
| Code Stability | rework rate (reverted or fixed-within-14d) | ≤ 2 % | ≥ 15 % | ✗ |
| | churn concentration on top-10 hot files (90d) | ≤ 20 % | ≥ 60 % | ✗ |
| Contributor Balance | top-contributor share of merged PRs (90d) | ≤ 25 % | ≥ 70 % | ✗ |
| | contributor entropy (normalized) | ≥ 0.9 | ≤ 0.4 | ✗ |
| Issue Health | issue resolution p85 | ≤ 7 d | ≥ 90 d | ✗ |
| | reopen rate | ≤ 3 % | ≥ 20 % | ✗ |
| | backlog growth (open-issues trend, 90d) | ≤ 0 | ≥ +50 % | ✗ |
| CI/CD Stability | default-branch CI success rate | ≥ 97 % | ≤ 85 % | ✗ |
| | flaky-run rate (conclusion flip-flop on rerun) | ≤ 2 % | ≥ 10 % | ✗ |

## 3. Normalization modes

1. **Absolute thresholds** (default) — the table above. Interpretable to a tech lead who has never
   seen the tool.
2. **Self-baseline** — compare each input against the repo's own trailing 90-day distribution to
   detect *change* rather than absolute level.

## 4. Validation plan (Phase 4)

1. Implement the health engine reading `health_config.yaml` (single source of truth — the backend
   and the tests read the same file).
2. Run it against 4–5 repositories from [ADR-001](decisions/ADR-001-training-repositories.md)
   whose condition is known (e.g. a repo in a documented slowdown, a repo with a bot-driven
   contribution spike).
3. Check the **ordering** is sensible: a repo in a slowdown should score lower on Delivery
   Velocity and PR Health; a single-maintainer repo should score lower on Contributor Balance.
4. Adjust thresholds, re-run, and record the final values **here** with `Validated? = ✓` and a note
   naming the repos used.
5. No health number is presented as authoritative before this run.

## 5. PR size buckets

| Bucket | Lines changed (filtered) |
|---|---|
| S | ≤ 100 |
| M | 101–500 |
| L | 501–1000 |
| XL | > 1000 |

## 6. Filtering rules (apply before any metric is computed)

- **Bots:** any account matching `*[bot]`, plus a configurable bot-login list (Dependabot, Renovate,
  semantic-release, etc.), flagged `is_bot`. Excluded from contributor and workload metrics;
  kept in the raw data so the filter is auditable.
- **Generated / vendored files** excluded from churn and PR size: lockfiles (`*.lock`,
  `package-lock.json`, `yarn.lock`, `poetry.lock`, `Cargo.lock`, `go.sum`, `composer.lock`), build
  output (`dist/`, `build/`, `out/`, `*.min.js`, `*.min.css`), vendored code (`vendor/`,
  `third_party/`), generated code (`*.generated.*`, `pb*.go`, OpenAPI clients), snapshots and
  fixture data. Flagged `is_generated` in `file_changes`, never deleted.
