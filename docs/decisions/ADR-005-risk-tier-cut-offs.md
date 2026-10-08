# ADR-005: Risk tier cut-offs

**Status:** Accepted · **Date:** 2026-10-08 · **Resolves:** Section 25, open decision 5

## Context

Section 8.6 says XGBoost with class weighting is usually **not calibrated**, and the UI should
show either a calibrated probability or **HIGH / MEDIUM / LOW tiers**. We must decide what
actually separates the tiers, and the choice changes what "HIGH risk" means to a user.

## Decision

**Tiers are defined by calibrated-probability thresholds chosen on the validation split, with a
percentile guardrail — not by raw model scores.**

1. Calibrate (isotonic, fallback Platt) on the validation slice; verify with a reliability curve.
2. Choose thresholds on validation precision/recall:
   - **HIGH:** calibrated p ≥ `t_high`, where `t_high` is set to target **precision ≥ 0.5** at
     the smallest threshold that still recalls a usable share of positives. "At least half of the
     PRs flagged HIGH really did regress" is the honest floor.
   - **LOW:** calibrated p < `t_low`, where `t_low` is the **base rate** (positive rate of the
     scored population) — below that, a PR is less likely risky than a random pick.
   - **MEDIUM:** everything between.
3. **Percentile guardrail:** if the calibrated thresholds place an implausible share of PRs in one
   tier (e.g. > 40 % HIGH), fall back to percentiles within the repo's scored PRs
   (top 10 % HIGH, next 25 % MEDIUM) and surface a warning in the evaluation report that the
   calibration was not trusted.
4. Thresholds are stored in `model_versions.metrics` JSONB alongside the model, so the tiers a
   user sees are traceable to a specific model version.

## Rationale

- Percentile-only tiers are self-referential: in a healthy repo, the "top 10 % riskiest" PRs may
  all be near-harmless. Calibrated thresholds keep HIGH meaningful across repos.
- But calibrated thresholds can also misbehave on a badly calibrated model, so the percentile
  fallback is the safety net rather than the primary.
- Anchoring `t_low` at the base rate is the decision-theoretic floor and needs no tuning.

## Consequences

- The UI shows the calibrated probability **and** the tier, and only ever says "78% chance" when
  the reliability curve actually supports reading it that way (Section 8.6). Otherwise it shows
  the tier plus the score's rank.
- Thresholds are reported in the Phase 7 evaluation report with the precision/recall they
  achieved — measured, not assumed.
