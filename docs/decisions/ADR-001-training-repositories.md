# ADR-001: Training repository list and selection criteria

**Status:** Accepted · **Date:** 2026-10-08 · **Resolves:** Section 25, open decision 1

## Context

Section 8.4 requires training on **multiple public repositories** (target 10–30 active repos,
mix of sizes and languages) rather than one repo, so the PR-risk model generalizes rather than
learning one project's idiosyncrasies.

## Decision

Select training repositories with these **selection criteria**:

1. Uses the GitHub pull-request workflow (not Gerrit / mailing-list patches).
2. **≥ 200 merged PRs in the trailing 24 months** — enough rows per repo for the label to be
   meaningful after the 14-day window and a time-based split.
3. Uses GitHub **issues** with a `bug`-type label (needed by the label heuristic in
   `docs/ml.md` §2). We verify a bug label exists before including the repo.
4. Not a generated-content or mirror repo (e.g. no `DefinitelyTyped`, no `awesome-*` lists,
   no auto-generated docs repos — they pollute churn and bot metrics).
5. Mix of **languages** (Python, JS/TS, Go, Rust, PHP, Ruby, Java, C#) and **sizes**
   (mid-size libraries to large platforms).

**Initial list (20 repositories):**

| Repository | Language | Why included |
|---|---|---|
| `pallets/flask` | Python | Mid-size, disciplined PR flow, bug labels |
| `fastapi/fastapi` | Python | Active, review-heavy, bug labels |
| `pydantic/pydantic` | Python | High PR volume, frequent releases |
| `pandas-dev/pandas` | Python | Large, complex, revert-prone merges |
| `scikit-learn/scikit-learn` | Python | Large, mature review process |
| `numpy/numpy` | Python | Large, scientific, long-lived codebase |
| `pytest-dev/pytest` | Python | Mid-size, active |
| `django/django` | Python | Large, trunk-based with strict review |
| `requests/requests` | Python | Small-mid, well-known |
| `vuejs/core` | JS/TS | High PR volume |
| `eslint/eslint` | JS/TS | Very active PR and bug-label culture |
| `prettier/prettier` | JS/TS | High volume, bot + human mix (filtering test) |
| `babel/babel` | JS/TS | Large, long-lived |
| `ant-design/ant-design` | JS/TS | Very high PR volume |
| `gohugoio/hugo` | Go | High volume, fast merge cadence |
| `grafana/grafana` | Go/TS | Large platform, mixed review maturity |
| `rust-lang/rust` | Rust | Very large; stress-tests scale caps |
| `laravel/laravel` | PHP | Large, active |
| `rails/rails` | Ruby | Large, long-lived, classic review process |
| `elastic/elasticsearch` | Java | Large platform, high churn |

## Rationale

A spread across languages and sizes guards against the model learning one project's conventions.
All listed repos are well-known, so a reviewer of this portfolio can sanity-check whether
predicted risk and SHAP factors look plausible.

## Consequences

- Ingestion cost is real: 20 repos × 24 months is a large number of API calls. The history-depth
  cap (ADR-006) and incremental sync with cursors bound it, and ingestion is a one-time cost per
  repo with cached raw payloads.
- A repo that turns out to have **< 30 positives** after labeling is excluded from training and
  reported in the evaluation doc (Section 8.2 rule), not silently kept.
- The list is stored as a config file (`ml/datasets/repos.yaml`) so it is versioned with the
  dataset, not hard-coded.
