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
| 2 | `POST /repositories/connect`, `GET /jobs/{job_id}` | ☐ |
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
