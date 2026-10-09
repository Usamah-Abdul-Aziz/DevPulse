# DevPulse — API reference

The live OpenAPI schema is served at `/docs` (Swagger UI) and `/openapi.json`.
This page documents the contracts and the conventions that do not fit a schema.

Base URL: `/api/v1`. All responses are JSON. All list endpoints are paginated.

---

## Conventions

- **Errors** use RFC 9457-style problem details:
  `{ "status": 404, "title": "Not Found", "detail": "..." }`.
- **Timestamps** are ISO 8601 with timezone offset (`2026-10-08T09:30:00+07:00`).
- **Durations** are returned as hours (float) so the frontend can format them;
  p50 and p85 are separate metric keys, never one field with an array.
- **Pagination**: `?page=1&limit=20`; responses carry
  `{ "items": [...], "page": 1, "limit": 20, "total": 123 }`.
- **Risk tiers** are `LOW` / `MEDIUM` / `HIGH` per
  [ADR-005](decisions/ADR-005-risk-tier-cut-offs.md).

## Endpoints by phase

| Phase | Endpoint | Status |
|---|---|---|
| 1 | `GET /healthz`, `GET /readyz` | ✅ implemented |
| 2 | `POST /repositories/connect`, `GET /repositories`, `GET /repositories/{id}`, `GET /jobs/{job_id}` | ✅ implemented |
| 3 | `GET /repositories/{id}/metrics`, `/activity`, `/demo` | ☐ |
| 4 | `GET /repositories/{id}/health` | ☐ |
| 5 | `GET /repositories/{id}/pull-requests` (rule tiers) | ☐ |
| 8 | `GET /pull-requests/{id}/risk` (score + SHAP) | ☐ |
| 9+ | `/hotspots`, `/anomalies` | ☐ (post-MVP) |

---

## Health (Phase 1)

### `GET /healthz` — liveness

Never touches dependencies. Use this for platform health checks.

```json
{
  "status": "ok",
  "service": "devpulse-backend",
  "version": "0.1.0",
  "environment": "production"
}
```

Returns **200** as long as the process can answer. A cold-starting Render
instance still returns 200 once it is accepting traffic.

### `GET /readyz` — readiness

Checks dependencies and **fails loudly**, naming the broken component. A load
balancer should route traffic away on a non-200.

```json
{
  "status": "ok",
  "service": "devpulse-backend",
  "version": "0.1.0",
  "components": [{ "name": "database", "status": "ok", "detail": null }]
}
```

On failure: **503** with the same shape and `status: "fail"`; the failing
component carries a truncated detail string (200 chars max, no secrets).

**Why two endpoints:** a sleeping free-tier instance is *live* but slow to be
*ready*. Splitting them lets the dashboard distinguish "waking up" from "broken"
([ADR-007](decisions/ADR-007-hosting-plan.md)).

---

## Repositories and jobs (Phase 2)

Ingestion is asynchronous: `connect` accepts the work and returns immediately, and the caller polls
the job until it lands
([ADR-009](decisions/ADR-009-ingestion-idempotency-and-resume.md)). Nothing about ingestion may
block a request (AGENTS.md, engineering invariant 5).

### `POST /repositories/connect`

Body: `{ "repository": "owner/name" }`. Accepts a bare `owner/name`, a full GitHub URL, or
`host/owner/name`, with or without a trailing `.git`; it is normalized and lower-cased, because
GitHub logins are case-insensitive.

Returns **202** — the request was accepted, the work has not finished:

```json
{ "job_id": 12, "repository_id": 3, "status": "pending" }
```

The `status` echoes what the job is *now*, so a re-connect of a repository mid-ingestion answers
`"running"` rather than `"pending"`.

| Status | Title | Condition |
|---|---|---|
| **422** | `Unprocessable Content` | body is not valid `owner/name` (FastAPI's validation envelope, not the problem-detail shape) |
| **400** | `Bad Request` | `ALLOWED_REPOS` is unset — **fail-closed**, with a detail explaining how to set it; or `GITHUB_TOKEN` is not configured |
| **403** | `Forbidden` | repository is not on the allow-list |

Re-connecting is idempotent and never starts a duplicate job:

| Existing job | Response |
|---|---|
| `pending` / `running` | 202 with that job id, no new job |
| `paused`, rate window not yet open | 202 with that job id, untouched |
| `paused`, rate window open | 202 with that job id, **re-queued in place** |
| `succeeded` / `failed` | a new *incremental* job (watermark = `last_synced_at`) |

### `GET /repositories`

`?page=1&limit=20`. `limit` is clamped to 1–100 and the response echoes what was actually applied.
Repositories are ordered newest-synced first, with never-synced repositories last.

```json
{
  "items": [
    {
      "id": 3,
      "full_name": "fastapi/fastapi",
      "owner": "fastapi",
      "name": "fastapi",
      "default_branch": "master",
      "last_synced_at": "2026-10-09T11:04:00+00:00",
      "is_demo": false
    }
  ],
  "page": 1,
  "limit": 20,
  "total": 1
}
```

### `GET /repositories/{id}`

The repository plus a `latest_job` summary. **404** (`title: "Not Found"`) on an unknown id.

```json
{
  "id": 3,
  "full_name": "fastapi/fastapi",
  "owner": "fastapi",
  "name": "fastapi",
  "default_branch": "master",
  "last_synced_at": "2026-10-09T11:04:00+00:00",
  "is_demo": false,
  "latest_job": {
    "id": 12,
    "status": "succeeded",
    "started_at": "2026-10-09T11:02:00+00:00",
    "finished_at": "2026-10-09T11:04:00+00:00",
    "resume_after": null,
    "counts": { "prs": 412, "commits": 3890, "issues": 207 },
    "error": null
  }
}
```

### `GET /jobs/{job_id}`

What the frontend polls every 2 s. **404** (`title: "Not Found"`) on an unknown job.

```json
{
  "id": 12,
  "repository_id": 3,
  "status": "paused",
  "started_at": "2026-10-09T11:02:00+00:00",
  "finished_at": null,
  "resume_after": "2026-10-09T12:00:00+00:00",
  "cursor": { "phase": "pull_requests", "cursors": { "pull_requests": "Y3Vyc29yMQ==" } },
  "counts": { "prs": 120, "api_calls": 3 },
  "error": null
}
```

Job status and what it means for a poller:

| `status` | Meaning | Keep polling? |
|---|---|---|
| `pending` | queued, not started yet | yes |
| `running` | ingesting | yes |
| `paused` | GitHub's rate budget ran out; the cursor and `resume_after` say where and when | **yes** — it resumes on its own once the window reopens |
| `succeeded` | done; `repositories.last_synced_at` updated | no |
| `failed` | `error` holds the backend's message, truncated to 500 chars, no traceback or secrets | no |

A `paused` job is deliberately not an error, and the frontend says so in plain language rather than
showing a failure — the rate limit is a condition GitHub guarantees on any large repository.
