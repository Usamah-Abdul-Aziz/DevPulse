# ADR-002: Label window and fix keywords

**Status:** Accepted · **Date:** 2026-10-08 · **Resolves:** Section 25, open decision 2

## Context

The `high_risk` label (Section 8.2) flags a PR as risky if a revert or a bug-fix follow-up lands
within a window after merge. The window and the fix-keyword list are free parameters that change
both the positive rate and the label noise.

## Decision

- **Label window: 14 days** after merge. The window is closed (label computable) only for PRs
  merged **≥ 14 days before the dataset extraction date**.
- **Fix keywords** (case-insensitive, matched on follow-up PR title **and** branch name):

  ```text
  fix, fixes, fixed, fixing, hotfix, regression, regressions, revert, reverts,
  reverted, bug, bugfix, bug fix, patch, resolve, resolves, resolved, correct
  ```

- **Revert detection:** a revert is any commit/PR whose message matches
  `^revert\s+...` or `This reverts commit <sha>` **and** references the original PR number or its
  merge SHA (direct reference in the revert body, or the reverted commit belongs to the PR).
- **Linked-bug requirement:** a follow-up PR counts only if it touches ≥ 1 of the same files,
  is merged within 14 days of the original merge, **and** either (a) links an issue carrying a
  bug-type label (`bug`, `bugfix`, `type: bug`, `kind/bug`, `regression`, `defect`), or (b) carries
  a fix keyword in title/branch.

## Rationale

- 14 days is short enough to stay attributable to the original change (a fix landing 6 months
  later is probably unrelated) and long enough to catch most real rework; it is a common choice
  in defect-prediction literature.
- Matching title **and** branch (not title alone) catches `fix/checkout-null`-style branches with
  generic titles, and matching keywords on the *follow-up* PR rather than the original avoids the
  trivial case where the original PR itself says "fix".
- Bug-label matching is union-based (`bug`-type label) because label vocabularies differ per repo;
  the per-repo label mapping lives in `ml/datasets/repos.yaml`.

## Consequences

- **Label noise is expected and documented** — this is a SZZ-lite heuristic, not ground truth.
  The label rules and their limitations are stated verbatim in `docs/ml.md` and in the UI wherever
  predictions are shown.
- The **positive rate is reported per repository** in the evaluation output, so a reader can see
  which repos are label-sparse.
- These exact values are recorded in the `dataset_version` metadata, so a dataset rebuilt with a
  different window is a new version, not a silent overwrite.
