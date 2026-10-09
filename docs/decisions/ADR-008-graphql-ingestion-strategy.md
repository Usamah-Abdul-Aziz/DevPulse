# ADR-008: GraphQL-first ingestion strategy

**Status:** Accepted · **Date:** 2026-10-09 · **Resolves:** Phase 2 ingestion transport and
incremental-sync mechanism

## Context

Blueprint §13.1 prefers the GraphQL API to cut request counts, and §5 lists the acceptance
criteria: idempotent re-run, resume after a rate-limit stop, bots and generated files flagged.
Before writing the queries we verified the arguments actually available on the published GitHub
GraphQL schema, and two of the four entity types do not behave the way an incremental sync wants:

| Connection | Pagination args | `since`? |
|---|---|---|
| `Repository.pullRequests` | `after before first last baseRefName headRefName labels orderBy states` | **no** |
| `Repository.issues` | `after before first last filterBy labels orderBy states` | **no** |
| `Commit.history` | `after before first last since until` | **yes** (`GitTimestamp`) |

So "fetch everything changed since `last_synced_at`" is not expressible for PRs and issues. Naively
paging the whole connection on every sync works but costs the entire rate budget each run — the
opposite of what the rate-limit acceptance criterion asks for.

## Decision

**GraphQL for everything except releases, which stay on REST** (GraphQL release objects are
available but the REST `/releases` endpoint is stable, simpler, and releases are low-volume).

Query plan (all in `backend/app/ingestion/queries.py`):

1. **Repository metadata** — `defaultBranchRef.name`, `pushedAt`, `pullRequests.totalCount`.
   The PR count drives the large-repo window reduction in [ADR-006](ADR-006-history-depth-cap.md).
2. **Pull requests** — one query pages `pullRequests(first: 100, orderBy: {field: UPDATED_AT,
   direction: DESC})` with `reviews(first: 100)` and `files(first: 100)` nested, so a page costs
   one call instead of 1 + 100 + 100. PRs whose file connection has more than the nested cap get
   follow-up `pullRequest(number:)` file queries up to
   `INGESTION_MAX_FILE_CHANGES_PER_PR` (1000), after which `truncated_files = true`.
   `PENDING` reviews are skipped — they are requested reviewers, not submitted reviews.
3. **Issues** — same shape and the same stop rule, plus `labels(first: 50)` and
   `timelineItems(itemTypes: [REOPENED_EVENT]) { totalCount }` for `reopened_count`.
4. **Commits** — `ref(qualifiedName: $branch).target { ... on Commit { history(first: 100, since:,
   until:) } }`. This is the one connection that *does* take a time filter, so the window is
   enforced server-side.
5. **Releases** — REST `/releases`, pages of 100, keeping only rows with `published_at`.

### The watermark rule (PRs and issues)

Because there is no `since`, incremental sync is expressed as paging *depth*:

```text
orderBy: UPDATED_AT DESC  →  stop when the oldest item on the page < watermark
```

where `watermark = max(window_start, last_synced_at)`. The page that straddles the watermark **is
loaded** and stored; only the *paging* stops there. Dropping it would lose PRs that were opened
before the window but updated inside it — a silent hole in the data. Rows with `created_at <
window_start` are dropped after the upsert decision, so a re-opened old issue does not enter the
24-month analytics window it does not belong to.

Every query also selects `rateLimit { remaining cost limit resetAt }`, so the budget is read from
the response body rather than estimated.

## Rationale

- **Nested connections are the big win.** A 100-PR page with reviews and files is one GraphQL call;
  the REST equivalent is 1 + 2×100. On a 24-month window of a few thousand PRs this is the
  difference between finishing in minutes and exhausting the budget.
- **UPDATED_AT-desc paging is the closest thing to `since` that the schema offers.** It puts the
  newest activity first, so an incremental run reads one or two pages and stops, while a full run
  reads down to `window_start`. Both use the identical code path — the only difference is the
  watermark value.
- **Server-side filtering for commits** is strictly better than the client-side rule and is used
  where the schema allows it.
- **REST for releases** avoids a query whose only value is uniformity; releases are a handful of
  rows per repo and page cheaply.

## Consequences

- **Incremental sync is not a delta, it is a bounded re-scan.** A repo where many old PRs were
  recently updated costs more than the item count suggests, because paging stops only at the
  watermark. The bound is the window, never the whole repository.
- **The watermark is applied per page, not per item.** A page of 100 straddling the watermark
  writes up to 100 rows, some of which predate it. This is deliberate (see above) and is asserted
  in `tests/ingestion/test_pipeline.py::TestWindowing`.
- **`orderBy: UPDATED_AT` is a sort, not a guarantee.** GitHub pages by the index, so a PR updated
  while a sync is mid-flight may be missed or fetched twice. Fetching twice is harmless (natural-key
  upsert, [ADR-009](ADR-009-ingestion-idempotency-and-resume.md)); being missed is caught by the
  next sync, since any later update bumps `updatedAt` past the new watermark.
- **GraphQL cost accounting is point-based**, not request-count-based. Heavy queries cost more
  points, which is why `files(first: 100)` is nested rather than queried per PR.
- **A repository with no default branch has no commit phase.** The pipeline skips commits rather
  than failing the job; the empty branch is recorded and the job still succeeds.
