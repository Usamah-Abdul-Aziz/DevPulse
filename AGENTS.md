# AGENTS.md — guidance for AI coding agents

This file is the contract for any AI agent (or human contributor) working in this repo. It encodes
the invariants of the project; the blueprint lives in `docs/` for the full reasoning.

## Follow the phase order

- Work through [`docs/roadmap.md`](docs/roadmap.md) in order. **Do not implement post-MVP features
  during the MVP** (Phases 0–8). "It would be easy to also add hotspots" is scope creep, not a win.
- Every phase ends with: **passing tests, updated docs, and a working deployed slice.**
- Prefer small, reviewable commits — one acceptance-criteria item per PR where practical.

## ML invariants (the ones that destroy credibility if broken)

1. **Prediction time is PR open.** Features must be **as-of** `pull_requests.created_at`. Never use
   review/merge/cycle-time data as a *model input* — those are *observed signals* shown in the UI.
2. **Never use unlabeled PRs for training.** Only PRs whose 14-day post-merge window has closed.
3. **Never fabricate a metric value.** Evaluation numbers come from reproducible scripts. If a
   number is a placeholder, label it as such in place. Report the positive rate next to every
   classification metric.
4. **Report honestly when the model barely beats the rule baseline.** A credible null result is
   worth more than an inflated one.
5. Present SHAP as **signed contributions**, never as additive percentages.

## Engineering invariants

1. **Do not add infrastructure** (Redis, Kafka, queues, webhooks) without a written ADR in
   `docs/decisions/` stating the reason. "It looks good on the stack list" is not a reason.
2. **Keep secrets out of the repo.** No tokens, no database URLs, no secret keys. Config comes from
   `.env`; when you add a config value, add it to `.env.example` in the same change.
3. **Training and serving must not drift.** `ml/` trains and evaluates; `backend/app/ml/` only
   loads a versioned artifact and scores. Feature code shared by both lives in **one** package
   imported by both.
4. **No heavy work in a request.** No SHAP, no model training inside an API handler — free-tier
   memory limits. Scoring is batch; results are stored and served as plain reads.
5. **Ingestion is async and resumable.** Respect GitHub rate limits (read headers, back off with
   jitter, resume from the stored cursor). Never block a request on ingestion.

## Data-ethics invariants

1. **No individual performance scores, no leaderboards.** Contributor views show
   distribution/concentration as a *team risk signal*. Wording matters: "signal to investigate",
   never "developer is slow".
2. Bots and generated files are **flagged** (`is_bot`, `is_generated`), not deleted — the filters
   stay auditable.
3. Label noise and model limitations are stated wherever predictions are shown.

## Testing expectations

Before marking work done:

- `pytest` passes; new logic has tests (metrics against fixed fixtures, ingestion against a mocked
  GitHub client, scoring end-to-end).
- `vitest` passes for changed frontend components.
- The ML leakage test (`test_features_are_as_of`) passes whenever features or labels are touched.

## Document as you go

- New decision → `docs/decisions/ADR-NNN-short-name.md` (Context / Decision / Rationale /
  Consequences). Date it, link it from the doc it affects.
- Changed API → update `docs/api.md` and the OpenAPI schemas together.
- Changed health thresholds → update `docs/metrics.md` **and** `health_config.yaml` together, and
  record the validation status.
