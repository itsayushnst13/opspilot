# Deployment (about 15 minutes, free tiers)

Status: **configs are provided and were checked locally, but the app has not been deployed by the author.** The Docker image
build could not be run in the build sandbox (no Docker daemon); the same file layout was simulated by hand and run with
`ENV=prod` against PostgreSQL 16, including the full browser flow. Expect to fix small things on the first real deploy and
record the URLs below once it is live.

## Option A (recommended): one Render service + Neon Postgres
One container serves the API and the built UI, so there is no CORS to configure.

1. **Database.** Create a free project at [neon.tech](https://neon.tech) (or Supabase). Copy the connection string
   (`postgresql://...?sslmode=require`).
2. **Push the repo to GitHub** (make sure `.env` is not committed: `.gitignore` covers it).
3. **Render** -> New -> Blueprint -> select the repo (reads `render.yaml`). When prompted, paste the Neon string into
   `DATABASE_URL`. `JWT_SECRET` is generated for you.
4. Optional: add `GEMINI_API_KEY` to turn on LLM mode. Optional: set `EXPOSE_DEMO_USERS=false` and `DEMO_PASSWORD` for a private deployment.
5. First boot creates the tables, seeds the synthetic data and indexes the knowledge base (~30 s). The free Render plan
   sleeps after inactivity, so the first request after a pause takes ~30-60 s: open the URL once before sharing it.
6. Smoke test: `curl https://<service>.onrender.com/api/health` -> `{"status":"ok",...}`, then sign in as analyst, upload an RFQ,
   sign out, sign in as approver, approve.

Deliverables to fill in once live:

| | URL |
|---|---|
| LIVE_DEMO_URL | `https://<service>.onrender.com` |
| API_DOCS_URL | `https://<service>.onrender.com/docs` |
| GITHUB_URL | `https://github.com/<you>/opspilot` |

## Option B: UI on Vercel, API on Render
Deploy the API as above. In Vercel import the repo with root directory `frontend`, and set
`VITE_API_URL=https://<service>.onrender.com`. On Render set `CORS_ORIGINS=https://<your-app>.vercel.app`.

## Local full stack
```bash
docker compose up --build        # http://localhost:8000 (Postgres + app)
```
or without Docker: see "Local setup" in the README.

## Running the LLM-mode evaluation (not measured by the author)
```bash
GEMINI_API_KEY=... python evals/run_all.py --llm     # writes evals/results/REPORT_llm.md
```
The Gemini request/response code is covered by mock-transport tests only. Treat the first live run as an integration test.
