# ADR-009: Ingestion idempotency and resume

**Status:** Accepted · **Date:** 2026-10-09 · **Resolves:** Phase 2 acceptance criteria 1 and 2
(idempotent re-run, resume after a rate-limit stop)

## Context

Two of Phase 2's three acceptance criteria are about running the same work more than once:

1. *Idempotent re-run* — connecting a repository twice, or re-running a job after a crash, must
   never duplicate rows or reset progress.
2. *Resumes after a rate-limit stop* — a job paused by the rate budget continues from where it
   stopped, not from the top of the repository.

The third (flagging bots and generated files) is covered by the cleaning rules in
`architecture.md` §5 and does not affect the write path.

## Decision

### Idempotency: natural-key upserts, no read-modify-write

Every ingestion write goes through `bulk_upsert` (`app/ingestion/db.py`), keyed on the entity's
natural key, never on a "does this row exist?" check:

| Table | Natural key (`ON CONFLICT` target) |
|---|---|
| `repositories` | `(owner, name)` |
| `contributors` | `(repository_id, github_id)` |
| `pull_requests` | `(repository_id, number)` |
| `pull_request_reviews` | `(pull_request_id, github_id)` |
| `issues` | `(repository_id, number)` |
| `file_changes` | `(pull_request_id, path)` |
| `commits` | `(repository_id, sha)` |
| `releases` | `(repository_id, tag)` |

`update_cols` lists only the mutable fields, so immutable ones (ids, natural keys) are never
rewritten. Re-ingesting an identical page therefore issues an `UPDATE` that sets the same values —
row counts stay flat, primary keys stay stable, and foreign keys never dangle.

The Postgres path is `INSERT ... ON CONFLICT ... DO UPDATE`. SQLite has no equivalent, and
`INSERT OR REPLACE` deletes and re-creates the conflicting row, which churns row ids and breaks
foreign keys pointing at them; on SQLite the helper falls back to a load-then-merge that preserves
ids. That path exists for the test suite (which runs on SQLite) — production runs on Postgres.

### Resume: a JSONB cursor committed after every page

`ingestion_jobs.cursor` holds an `IngestionCursor`:

```json
{
  "phase": "pull_requests",
  "cursors": { "pull_requests": "Y3Vyc29yMQ==", "issues": null },
  "window_start": "2024-10-09T00:00:00+00:00",
  "window_end": "2026-10-09T11:00:00+00:00",
  "history_months": 24,
  "mode": "incremental"
}
```

The pipeline commits the session **after each fetched page**, not only at the end of a phase. A job
that stops loses at most one page of work, and resume restarts at the next page rather than
re-running the phase.

### The `paused` state and connect-time resume policy

GitHub's rate budget is checked *before* it hits zero (`INGESTION_MIN_RATE_BUDGET`, default 200
points). When it runs out the client raises `RateLimitExhausted` carrying the reset time; the
runner sets `status = "paused"` and `resume_after = resetAt`, and leaves the cursor in place. The
runner's other exception path is the contrast: anything else marks the job `failed` with a
truncated (≤500 char) error message and no traceback or secret material.

`POST /repositories/connect` decides what to do with an existing job:

| Existing job | Connect response |
|---|---|
| `pending` or `running` | **202 with that job id** — the connect is a no-op, not a duplicate |
| `paused`, `resume_after` not yet passed | 202 with that job id, untouched |
| `paused`, `resume_after` passed | 202 with that job id, **re-queued in place** |
| `succeeded` or `failed` | a new **incremental** job (`mode: "incremental"`, watermark =
`last_synced_at`) |

The deliberate detail: `_existing_job` returns a paused row *even when it is due to resume*. The
caller re-queues that exact row — `status` flipped back to `pending` — instead of inserting a new
one, so the stored cursor and its page position survive.

## Rationale

- **Upsert beats existence checks under concurrency.** A check-then-insert races with itself; a
  conflict-targeted upsert is atomic and is also what makes re-ingestion a no-op rather than an
  error.
- **Natural keys are what GitHub guarantees.** PR and issue numbers are stable per repository, the
  GraphQL `id` is stable per node, and the SHA identifies a commit. Row ids are ours and have
  nothing to do with identity.
- **Page-granular persistence is what makes resume honest.** Committing only at phase end would
  make "resume after a rate-limit stop" true only at phase boundaries — and rate limits do not
  wait for phase boundaries.
- **Pausing is a state, not an error.** Reporting `paused` lets the UI say "rate limited, will
  resume from the `pull_requests` phase" instead of showing a failure for a condition GitHub
  guarantees will happen on any large repository.
- **`resume_after` is GitHub's reset time, not a guess.** The cursor plus the reset time is enough
  for a future scheduler to resume automatically; today a connect request triggers it.

## Consequences

- **A re-run is only a no-op for identical input.** A PR whose `updatedAt` moved is rewritten with
  new values — which is the desired behaviour for an incremental sync, but means "idempotent"
  here means *no duplicate rows and no lost progress*, not *no writes*.
- **Only the job that owns the cursor may resume it.** There is no claim token; correctness relies
  on at most one runner per repository, which FastAPI background tasks satisfy within a single
  process. A second worker would need a lock before this assumption holds.
- **Counts are per-run, not cumulative.** `ingestion_jobs.counts` describes the work that job did;
  a resumed job's counts restart from zero for the resumed portion. Total row counts come from the
  tables, not from summing jobs.
- **`file_changes.commit_id` is deliberately nullable** and unfilled in Phase 2 — attributing a
  file change to a specific commit needs per-commit patch data that the PR query does not return.
  It is left null rather than guessed.
- **A paused job stays paused until something reconnects.** Phase 2 does not run a scheduler;
  resuming requires a `POST /connect` after `resume_after`. Phase 13's status page is the natural
  place to surface a long-paused job.
