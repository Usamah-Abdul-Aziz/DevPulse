# ADR-007: Hosting plan and free-tier fallback

**Status:** Accepted · **Date:** 2026-10-08 · **Resolves:** Section 25, open decision 7

## Context

Section 19 targets **Rp0** for development and the portfolio demo on free tiers: Vercel Hobby
(frontend), Render Free (backend), Supabase Free (database). Free tiers change; the blueprint
itself says to verify current limits before promising them publicly. We need a written plan for
what happens when a free tier turns out to be insufficient.

## Decision

**Step 0 — Verify before promising (Phase 1, concrete checks):**

| Concern | Check | Fallback if it fails |
|---|---|---|
| Render Free sleeps after inactivity (~15 min), 750 h/month | Measure cold-start time; if > ~10 s hurts the demo, pre-computed demo data still loads instantly from Supabase, and the frontend shows a "waking up the server" state | Move backend to **Fly.io free allowance** or a **Hetzner CX11 VPS (~Rp 80k/bln)** |
| Supabase Free pauses the DB after ~1 week inactivity, 500 MB storage, 2 GB egress | Verify the demo row set fits in 500 MB (it will — 24 months of one repo); keep the project active with a scheduled health-check ping | Move DB to **Neon** (free, no auto-pause on the free tier at time of writing — re-verify) or run Postgres on the same VPS |
| Render/Supabase instance RAM (512 MB class) | Batch scoring and SHAP must fit; training is always local | Cap batch scoring job memory; fall back to the VPS plan |
| GitHub Actions free minutes | Cache pip/npm, split `backend.yml` / `frontend.yml` / `ml.yml` | Run heavy ML CI only on PRs touching `ml/` |

**Step 1 — Fallback tier (same architecture, cheap host):**
one small VPS (Hetzner CX11 or equivalent) running the backend + Postgres, with the frontend
still on Vercel. This costs a few dollars a month and removes sleep/pause limits entirely. It is
the preferred fallback because it changes **no code**, only deployment config.

**Step 2 — If a managed DB is needed:** Neon or Supabase Pro.

## Rationale

The fallback ladder is ordered by **cost then effort**: verify the free tier works → move compute
to a cheap VPS (no code change) → pay for a managed DB. No step requires re-architecting, and the
pre-computed demo (ADR-003) already removes the cold-start problem from the critical path.

## Consequences

- **No public promise is made until the Step 0 checks are run** and the numbers are recorded in
  `docs/` (Phase 1 exit criterion). The README's deployment section states the verified limits.
- Docker Compose parity (Section 16) means the local dev environment and the VPS deploy are the
  same image, so the fallback is a deploy change, not a port.
