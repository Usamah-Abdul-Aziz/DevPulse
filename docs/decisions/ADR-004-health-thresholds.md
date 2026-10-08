# ADR-004: Health score thresholds

**Status:** Accepted · **Date:** 2026-10-08 · **Resolves:** Section 25, open decision 4

## Context

Section 7.3 requires each health-score input to map to 0–100 by **linear interpolation between a
"good" and a "poor" threshold**, stored in a versioned `health_config.yaml`. Without initial
values the score cannot be computed at all; without a validation step the numbers are arbitrary.

## Decision

Use **absolute thresholds as the default mode**, with the initial values below. These are
**starting points to be validated**, not calibrated truths.

| Component | Input | Good (→ 100) | Poor (→ 0) |
|---|---|---|---|
| Delivery Velocity | merged PRs/week, trend vs trailing 90d | ≥ 1.25× baseline | ≤ 0.70× baseline |
| | releases per 90 days | ≥ 4 | 0 |
| PR Health | pickup time p85 | ≤ 4 h | ≥ 72 h |
| | cycle time p85 | ≤ 24 h | ≥ 168 h (7 d) |
| | share of XL PRs (> 1000 lines changed) | ≤ 5 % | ≥ 30 % |
| Code Stability | rework rate (PRs reverted or fixed-within-14d) | ≤ 2 % | ≥ 15 % |
| | churn concentration on top-10 hot files, trailing 90d | ≤ 20 % | ≥ 60 % |
| Contributor Balance | top-contributor share of merged PRs, trailing 90d | ≤ 25 % | ≥ 70 % |
| | contributor entropy (normalized) | ≥ 0.9 | ≤ 0.4 |
| Issue Health | issue resolution p85 | ≤ 7 d | ≥ 90 d |
| | reopen rate | ≤ 3 % | ≥ 20 % |
| | backlog growth (open issues trend, 90d) | ≤ 0 | ≥ +50 % |
| CI/CD Stability | default-branch CI success rate | ≥ 97 % | ≤ 85 % |
| | flaky-run rate (conclusion flip-flop on rerun) | ≤ 2 % | ≥ 10 % |

**Values outside the range clamp to 0–100**; inputs with **no data** cause the component to be
excluded and the weights renormalized (Section 7.1), with the excluded components listed in the UI.

**Validation plan:** after the health engine exists (Phase 4), run it against 4–5 repos with
known conditions (ADR-001 list) and check the ordering is sensible — e.g. repos in a known
slowdown period should score lower on Delivery Velocity. Final validated values are written back
into `health_config.yaml` and documented in `docs/metrics.md`.

**Second mode (self-baseline)** remains implemented but not default: it compares each input
against the repo's own trailing 90-day distribution to detect *change* rather than absolute level.

## Rationale

Absolute thresholds make the score interpretable to a tech lead who has never seen the tool
("pickup p85 of 30 hours is objectively slow"), which serves the Monday-triage scenario better
than a purely relative score. Self-baseline stays available for repos whose baseline is unusual.

## Consequences

- The config file is the single source of truth — the same YAML is read by the backend and by the
  tests, so a threshold change is one edit, not a code change.
- **Every threshold is flagged as unvalidated until the Phase 4 validation run**, and the docs say
  so. No health number is presented as authoritative before that.
