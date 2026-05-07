# Deployment

ReliabilityGraph deploys as one Render web service. The Docker image builds the React frontend, serves it from FastAPI, runs the API, streams answers over SSE, stores local data in SQLite, calls the configured LLM/search providers, and loads the local entailment verifier.

## Render Service

Use the root `render.yaml` blueprint.

The blueprint creates:

- one Docker web service named `reliabilitygraph`
- a persistent disk at `/app/data`
- SQLite at `/app/data/reliability_graph.sqlite`
- public-demo access control
- server-side provider/search keys from environment secrets
- browser key management disabled

Set these Render secret values during blueprint creation:

```text
RELIABILITY_GRAPH_ACCESS_TOKEN=<shared access code for invited testers>
RELIABILITY_GRAPH_SECRET=<long random secret, at least 32 chars>
TINKER_API_KEY=<server-side Tinker key>
TAVILY_API_KEY=<server-side Tavily key>
TINKER_MODEL=<Tinker model or sampler checkpoint path>
```

Do not put keys in `render.yaml`, frontend env vars, screenshots, docs, or commits.

## Expected URL

After deploy, Render gives the app a URL like:

```text
https://reliabilitygraph.onrender.com
```

Share that URL plus the access code. Do not share provider keys with testers.

## Required Checks

Health:

```bash
curl https://<render-service>.onrender.com/health
```

Expected public response:

```json
{
  "status": "ok",
  "public_demo": true,
  "access_required": true,
  "verifier": {
    "ready": true
  }
}
```

Browser smoke:

1. Open the Render URL.
2. Enter the access code.
3. Confirm Settings shows Tinker connected from env and Tavily active from env.
4. Ask: `What changed in Python 3.14? Cite sources.`
5. Confirm the answer streams first.
6. Confirm Reliability Score appears only after checking completes.
7. Confirm citations open source URLs.
8. Confirm no plaintext key appears in Settings, activity, export, or browser devtools responses.

## Plan Choice

The blueprint uses `plan: standard` and a 1 GB disk because the app runs SQLite plus an ONNX entailment verifier. Free Render web services have an ephemeral filesystem and do not support persistent disks, so they are not appropriate for a durable shared demo.

For a temporary free demo, change `plan` to `free` and remove the `disk` block. Expect chat history and locally stored data to reset on redeploy, restart, or idle spin-down, and expect verifier memory pressure.

## Security Defaults

- API routes require the access-code session in public demo mode.
- The frontend shell, static assets, health check, and access endpoints are public so the app can load.
- Provider/search key management is disabled in the browser.
- Tinker and Tavily keys are read only from server-side env vars.
- Responses include security headers, including frame blocking and a same-origin content security policy.
- Each browser session gets an isolated demo user scope.
- Rate limiting is enabled per IP/session bucket.

## Limits

This is a controlled demo deployment, not hosted SaaS. It has no billing, admin console, account recovery, per-user budget accounting, or abuse moderation beyond the access code and rate limit. Rotate provider keys after a broad demo or if the access code leaks.
