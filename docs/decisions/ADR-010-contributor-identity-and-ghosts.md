# ADR-010: Contributor identity and ghost users

**Status:** Accepted · **Date:** 2026-10-09 · **Resolves:** Contributor keying and deleted-account
handling in Phase 2

## Context

Blueprint §13.3 says to "merge author identities", and blueprint §4 flags bot accounts and deleted
users as cleaning concerns. Two facts about the GitHub API make this harder than it looks:

1. **GitHub logins are mutable.** A user can rename their account; the old login then either
   resolves to nobody or, eventually, to someone else.
2. **Deleted accounts come back as `author: null`.** GraphQL returns no node at all for a user who
   has deleted their account, so there is no id, no login, and no way to recover one.

Keying contributors by login would therefore slowly corrupt the data: a rename would create a
second row for the same person, and a deleted user would drop their attribution entirely.

## Decision

### Key contributors by GraphQL node id, not login

`contributors` is keyed on `(repository_id, github_id)`, where `github_id` is the GraphQL node `id`
— a stable, immutable identifier. The login is stored as a *mutable attribute* and refreshed on
every encounter:

```python
# GitHub logins are mutable; the node id is the stable key. Refresh a renamed login so
# the UI never shows a handle GitHub stopped answering to (ADR-010).
if login and login != contributor.login:
    contributor.login = login
```

So a rename updates one row instead of creating a second one, and the UI always shows the handle
GitHub is currently answering to.

### Ghosts are real rows, never silently dropped

When `author` is null the pipeline writes a placeholder contributor with
`github_id = GHOST_GITHUB_ID` (`"GHOST"`) and `is_ghost = true`, and attributes the work to it.
`GHOST` cannot collide with a real node id, which is base64 of a scoped prefix (`04:User…`).

The attribution is preserved in two places:

- **`commits.author_name` / `commits.author_email`** are always populated from the commit object,
  because a commit records its author's name and email in the git payload even when the GitHub
  account is gone. This is the only entity where a deleted user's identity survives.
- **`pull_requests.raw_payload`** keeps the full GraphQL node for PRs, so the original payload is
  re-inspectable without a re-fetch.

### Bots are flagged by the same resolver, in one place

`is_bot` is set from the GraphQL `isBot` field where GitHub provides it, OR from an explicit
auditable rule list in `app/ingestion/cleaning.py` — a `[bot]` suffix check plus a curated list
(`dependabot`, `renovate`, `github-actions`, `pre-commit-ci`, `mergify`, `imgbot`, `greenkeeper`,
`sonarsource`, …). Per [AGENTS.md](../../AGENTS.md) data-ethics invariant 2, both bots and
generated files are **flagged, never deleted** — the rules are plain Python lists anyone can read
and audit.

## Rationale

- **The node id is the only stable handle GitHub offers.** Everything else — login, email, avatar —
  can change or be reused. Keying on it makes identity a property of the account rather than of a
  string the account can change.
- **Refreshing the login is the cheap half of "merge identities".** It keeps the display name
  current without any merge machinery.
- **A ghost row makes absence visible.** Dropping the attribution would silently understate the
  work attributable to humans; attributing it to `GHOST` keeps the count honest and lets Phase 3's
  metrics exclude `is_ghost` (and `is_bot`) explicitly rather than by accident.
- **Commit author metadata is irreplaceable.** Once the account is gone the email is the last
  evidence that a real person wrote that commit; storing it is what keeps a ghost from becoming
  an anonymous row.
- **An explicit bot list instead of a heuristic.** A login suffix check alone misses
  `dependabot`; a model-based classifier is unauditable. A list is boring, readable, and easy to
  challenge.

## Consequences — including the limitation we are not solving

- **There is no true identity merging in v1.** GitHub's API exposes no email→login mapping, so two
  rows for one person who committed from two different accounts (or with two emails on one account)
  stay separate. `contributors` is per-repository and per-account, not per-human. This is a real
  limitation and it is stated here rather than papered over; any future merging needs either
  GitHub's own identity data or a manually maintained alias table.
- **Ghost rows are repository-scoped placeholders.** Each repository gets its own `GHOST` row
  (`(repository_id, github_id)` is the key), so ghosts are not shared across repos. That is
  intentional — it keeps contributor counts per repository correct — but it means there is no
  single "deleted users" identity either.
- **`is_bot` and `is_ghost` are the exclusion contract for every downstream metric.** Phases 3–5
  must filter on them explicitly; a metric that forgets will be visibly wrong rather than subtly
  wrong, because `GHOST` and bot rows are ordinary rows.
- **The bot list needs maintenance.** New bots appear on GitHub regularly; the list is code, so
  adding one is a reviewed change with a test in `tests/ingestion/test_cleaning.py`, not a config
  edit nobody sees.
- **Renaming is eventually consistent.** Between the rename and the next ingestion, a contributor
  row shows its previous login. The refresh fixes it on the next sync rather than retroactively.
