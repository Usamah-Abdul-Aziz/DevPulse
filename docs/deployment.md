# Deployment

```text
Frontend → Vercel Hobby · Backend → Render Free · Database → Supabase Free
```

Target: **Rp0** for development and the portfolio demo, inside free-tier limits.
This page is the runbook; the *limits themselves* are verified per
[ADR-007](decisions/ADR-007-hosting-plan.md), which also defines the fallback ladder.

---

## Local (Docker Compose)

```bash
cp .env.example .env        # fill in GITHUB_TOKEN and ALLOWED_REPOS
docker compose up --build
```

- Frontend: <http://localhost:3000>
- Backend: <http://localhost:8000> · Swagger UI: <http://localhost:8000/docs>
- Postgres: `localhost:5432` (user/password/db: `devpulse`)

The compose file is the **production parity environment**: the same Dockerfile
runs on Render, so a deploy is a config change, not a port.

## Local without Docker

```bash
# Backend
cd backend
python -m venv .venv && .venv/Scripts/activate    # or: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload

# Frontend (separate terminal)
cd frontend
npm install --legacy-peer-deps
npm run dev
```

A Postgres instance is required for `readyz` to report the database component;
without it, `/healthz` still answers 200 (liveness is dependency-free).

---

## Deploying the MVP (Phase 1 onwards)

### 1. Database — Supabase

1. Create a project (free tier), pick a region close to the Render region.
2. Copy the **connection string** (Session/Transaction pooler, port 6543).
3. Store it in Render as `DATABASE_URL`.

**Verify the free tier:** project auto-pauses after ~1 week of inactivity, 500 MB
storage, 2 GB egress. Keep the project warm with a scheduled `GET /healthz` ping
(e.g. UptimeRobot, or a GitHub Action on a cron).

### 2. Backend — Render

1. New → Web Service → connect the repo → **Docker** runtime.
   `render.yaml` in `backend/` pre-fills everything; or set:
   - Build/Start: the Dockerfile (it is the compose image).
   - Health check: **`/healthz`**.
2. Environment variables (never committed — see `.env.example`):

   | Key | Value |
   |---|---|
   | `ENVIRONMENT` | `production` |
   | `DATABASE_URL` | Supabase pooler URL |
   | `SECRET_KEY` | `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
   | `GITHUB_TOKEN` | read-only, public-repo scope |
   | `ALLOWED_REPOS` | `fastapi/fastapi,pallets/flask` |
   | `FRONTEND_ORIGIN` | the Vercel URL |

3. Run migrations once the service is up:

   ```bash
   render ssh
   cd /app && alembic upgrade head
   ```

**Verify the free tier:** 750 instance-hours/month, sleeps after ~15 min idle,
512 MB RAM. Measure the cold start; the frontend must show its "waking up the
server" state, and the demo must load from pre-computed data (see
[product.md §8](product.md#8-demo-mode)).

### 3. Frontend — Vercel

1. New Project → import the repo → **Root Directory: `frontend`**.
2. Framework preset: **Next.js** (vercel.json applies automatically).
3. Environment variables:

   | Key | Value |
   |---|---|
   | `NEXT_PUBLIC_API_URL` | the Render backend URL |

4. `NEXT_PUBLIC_*` variables are inlined at build time — **redeploy after
   changing them**.

---

## Phase 1 exit checklist

- [ ] `/docs` reachable on the public Render URL.
- [ ] Landing page + dashboard reachable on the public Vercel URL.
- [ ] The dashboard's "API connection" card shows **Connected** cross-origin
      (CORS verified end to end, not just locally).
- [ ] `GET /healthz` is Render's health check and returns 200 after a cold start.
- [ ] Free-tier measurements recorded below (ADR-007 Step 0).

### Free-tier measurements

Fill in during Phase 1; these are the numbers the README's deployment section
quotes.

| Measurement | Value | Date |
|---|---|---|
| Backend cold-start time (Render Free) | _pending_ | — |
| Frontend initial load (demo, warm backend) | _pending_ | — |
| Frontend initial load (demo, cold backend) | _pending_ | — |
| Supabase DB size after demo ingest | _pending_ | — |
| Memory peak during batch scoring | _pending_ | — |

## Rollback / fallback

Per [ADR-007](decisions/ADR-007-hosting-plan.md), the ladder is:

1. **Free tiers** (default).
2. **Cheap VPS** (Hetzner CX11-class) running the same Docker images — no code
   change, only deploy config.
3. **Managed DB** (Neon / Supabase Pro) if storage or pause limits bind.

Reverting a bad backend deploy: Render keeps prior deploys — redeploy from the
dashboard. Database changes go through Alembic, so a schema rollback is
`alembic downgrade -1` against the documented revision.
