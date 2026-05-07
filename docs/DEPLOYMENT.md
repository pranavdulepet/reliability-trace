# Deployment

ReliabilityGraph has two deployable parts:

- Frontend: static React build. This can live at `https://pranavdulepet.github.io/reliability/`.
- Backend: FastAPI, SQLite, provider calls, Tavily retrieval, and the NLI verifier. This cannot run on GitHub Pages and needs a server such as Render.

Do not put Tinker or Tavily keys in the frontend. Configure them as backend environment secrets.

## Backend On Render

Use `render.yaml` as the starting blueprint. Set these secrets in Render:

```text
RELIABILITY_GRAPH_ACCESS_TOKEN=<shared demo access code>
RELIABILITY_GRAPH_SECRET=<long random secret>
TINKER_API_KEY=<server-side tinker key>
TAVILY_API_KEY=<server-side tavily key>
```

The blueprint sets:

```text
RELIABILITY_GRAPH_PUBLIC_DEMO=true
RELIABILITY_GRAPH_ALLOW_KEY_MANAGEMENT=false
RELIABILITY_GRAPH_COOKIE_SECURE=true
CORS_ORIGINS=https://pranavdulepet.github.io
```

That means demo visitors enter an access code, browser-side key editing is disabled, and provider/search keys stay server-side. Each browser session gets its own local conversation scope. The backend rate limit defaults to 120 API requests per hour per session/IP bucket, including access-code attempts.

Render Free is useful for a demo link, but its local filesystem is ephemeral. The SQLite conversation/audit store can reset after redeploys, restarts, or idle spin-downs. For a durable demo, upgrade the service and attach a persistent disk mounted at `/app/data`, or migrate storage to Postgres.

Check the backend after deploy:

```bash
curl https://<render-service>.onrender.com/health
```

Expected:

- `status: "ok"`
- `access_required: true`
- `public_demo: true`
- `verifier.ready: true`

If the verifier is not ready, the Docker build did not download the ONNX model. Rebuild the service and check build logs for `scripts/setup_nli_verifier.py`.

## Frontend At `/reliability`

Build the static frontend with the backend URL and `/reliability/` base path:

```bash
cd frontend
VITE_API_BASE=https://<render-service>.onrender.com npm run build:pages
```

Copy `frontend/dist/*` into the `reliability/` folder of the `pranavdulepet.github.io` website repo, then commit and push that website repo.

The deployed page should be:

```text
https://pranavdulepet.github.io/reliability/
```

## Safety Checklist

- Backend uses HTTPS.
- `RELIABILITY_GRAPH_ACCESS_TOKEN` is set.
- `RELIABILITY_GRAPH_SECRET` is set and not reused as a provider key.
- Tinker/Tavily keys are only backend env vars.
- `RELIABILITY_GRAPH_ALLOW_KEY_MANAGEMENT=false` in public demo mode.
- `CORS_ORIGINS` contains only `https://pranavdulepet.github.io`.
- The frontend was built with `VITE_API_BASE=https://<render-service>.onrender.com`.
- A test browser can log in, send a prompt, stream an answer, and see a final Reliability Score.

## Current Limits

This is a demo, not hosted SaaS. Browser sessions are isolated in SQLite by a signed session cookie, but there is no account recovery, admin console, quota billing, or abuse prevention beyond the access code and rate limit. Do not invite untrusted public traffic without adding real authentication and per-user billing/quotas.
