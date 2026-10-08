# DevPulse — Machine Learning

This document defines the ML system: the PR-risk prediction problem, labels, features, dataset,
evaluation protocol, explainability, and the post-MVP intelligence features. Threshold values for
the health score live in [`metrics.md`](metrics.md).

> **Standing rules for every number in this document and in the UI:**
> 1. Never publish a metric value that was not produced by a reproducible script on real data.
> 2. Numbers in docs that are illustrative placeholders must be labeled as such.
> 3. Report the **positive rate** next to every classification metric.

---

## 1. Problem statement

> At the moment a PR is **opened**, estimate the likelihood that it will cause rework or regression
> after merge, and explain the main contributing factors.

**Prediction time is PR open.** Only information available at that moment may be used as a
feature. Review-derived signals (review count, review delay, cycle time) are known only later;
they are shown in the UI as *observed signals*, not model inputs. (A second, post-review model is
optional future work.)

## 2. Label definition

```text
high_risk = 1  if, within 14 days after merge, at least one holds:
  (a) a revert commit/PR references this PR or its merge commit
  (b) a follow-up PR that touches ≥1 of the same files, merged within 14 days,
      and is linked to a bug issue (bug-type label) or carries a fix keyword
      (fix, hotfix, regression) in title/branch
high_risk = 0  otherwise (only for PRs old enough that the 14-day window has closed)
```

Rules:

- This is a **SZZ-lite approximation** — a documented heuristic, not ground truth. **Label noise
  is expected** and must be stated wherever predictions are shown.
- The exact window (14 days) and fix-keyword list are fixed in
  [ADR-002](decisions/ADR-002-label-window-and-keywords.md) and recorded in `dataset_version`
  metadata; changing them produces a new dataset version.
- Report the **positive rate per repository**. If positives are too few (**< 30 per training
  repo**), exclude the repo or pool it — the choice is recorded in the evaluation report.
- Do not describe labels as developer quality or blame.
- Unmerged and still-open PRs are scored, but **never** used as labeled training rows.

## 3. Features (all computed *as-of* PR creation time)

| Group | Features |
|---|---|
| Size | `lines_added`, `lines_deleted`, `files_changed`, `dirs_touched` (filtered for generated files) |
| File history | `file_prior_change_count_90d`, `file_prior_churn_90d`, `file_prior_bugfix_count_180d` (max / mean across touched files) |
| Author history | `author_prior_merged_prs`, `author_prior_risk_rate` (labeled history before this PR only), `author_familiarity_with_files` |
| Context | `day_of_week`, `hour_opened`, `is_draft_at_open`, `has_tests_changed`, `has_linked_issue` |

`file_hotspot_score` (the [Phase 9](#51-code-hotspots-phase-9) composite) is **not** an MVP feature;
the file-history features above are its raw ingredients.

**Leakage rule:** every historical aggregate must be computed from data with timestamp < PR
`created_at`. An automated test (`test_features_are_as_of`) recomputes features at a past cut-off
and asserts no later data was used.

## 4. Dataset and evaluation

### 4.1 Dataset

- Train on **multiple public repositories** — the initial 20-repo list and selection criteria are
  fixed in [ADR-001](decisions/ADR-001-training-repositories.md).
- Store a **versioned dataset snapshot** (`dataset_version`) recording: extraction date, repo list
  and their per-repo stats, label rules (window + keywords), history window
  ([ADR-006](decisions/ADR-006-history-depth-cap.md)), and feature version.

### 4.2 Evaluation protocol

- **Time-based split:** train on earlier PRs, validate/test on later PRs. No random split.
- **Cross-repo check:** hold out whole repositories to estimate generalization.
- **Models, in order:** (1) rule-based baseline from Phase 5, (2) Logistic Regression,
  (3) Random Forest, (4) XGBoost.
- **Metrics:** PR-AUC (primary, for imbalance), ROC-AUC, precision/recall at the chosen threshold,
  **precision@k / recall@k** for the top-k riskiest PRs (matches how a lead uses it), Brier score
  and calibration curve.
- Report the **positive rate** next to every metric.
- **Report honestly if XGBoost is only marginally better than the rule baseline.** That is a valid,
  credible result.

### 4.3 Probability and risk tiers

XGBoost with class weighting is **not calibrated**. Calibrate (isotonic, or Platt as fallback) on a
validation slice, check the calibration curve, then either show the calibrated probability or show
**risk tiers** (HIGH / MEDIUM / LOW). Tier cut-offs are defined in
[ADR-005](decisions/ADR-005-risk-tier-cut-offs.md): calibrated thresholds chosen on validation
(precision ≥ 0.5 floor for HIGH; base rate as the LOW boundary), with a percentile fallback if the
calibration is not trustworthy. Avoid wording like "78% chance of regression" unless the
reliability curve supports it.

## 5. Explainability (SHAP)

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

Show a ranked, signed contribution bar chart. Do **not** present SHAP values as
"+24%, +21%, … = 91%".

SHAP is computed **in batch at scoring time** and stored (in `risk_predictions.shap` JSONB), not
calculated live per request.

---

## 6. Post-MVP intelligence features

### 6.1 Code hotspots (Phase 9)

```text
Hotspot Score (0–100) = normalized( change_frequency × code_churn ,
                                    with recency decay )
                        combined with historical bug-fix touches
```

- Computed per file from `file_changes`, with time decay (recent changes matter more).
- Optional: complexity metrics where cheaply available.
- A hotspot means "deserves attention", not "bad code". Display as a **score**, not a probability.

### 6.2 Anomaly detection (Phase 10)

- Start with a **robust z-score / MAD** baseline on weekly series (commits, merged PRs, churn,
  p85 cycle time).
- Compare with **Isolation Forest** on multi-feature weekly vectors; keep it only if it adds value.
- Require sufficient history (**≥ 26 weeks**) per repo before alerting; otherwise show
  "insufficient data".
- Bots and generated files are filtered before computing features.
- An anomaly is a signal to investigate, **not** evidence of a problem or wrongdoing.

### 6.3 Delivery delay prediction (Phase 11)

- Target: **binary** — pickup time (or cycle time) greater than the repository's own p75.
- Features known at PR open: size, files changed, number of requested reviewers, day/time opened,
  historical pickup time of the touched area.
- Evaluate with the same protocol as §4.2.

### 6.4 Recommendation engine (Phase 12)

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
