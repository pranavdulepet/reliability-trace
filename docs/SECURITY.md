# Security Notes

## API Keys

Provider keys are accepted only by backend endpoints. They are encrypted with a local Fernet key before being stored in SQLite. In local mode, the master secret comes from `RELIABILITY_GRAPH_SECRET`; if absent, the backend creates an ignored local secret file under `data/`.

The API returns only:

- provider
- key fingerprint
- status
- created time
- last-used time

It never returns plaintext keys.

## Object Scope

Every stored object has a `user_id`. Local mode defaults to `local`, but the API still routes reads and writes through that scope so hosted auth can replace the local user resolver later.

## Prompt And Document Safety

Retrieved text must be treated as evidence only. It must not override system or developer instructions. The pipeline should pass source-bound snippets, source IDs, and extraction tasks rather than unbounded retrieved pages.

Fetched URLs are blocked if they contain credentials, resolve to loopback/private/link-local/reserved networks, redirect into blocked networks, return unsupported content types, or exceed the fetch size cap. The frontend also limits per-message attachment count and file size.

Provider and fetch errors are sanitized before reaching API responses, SSE events, run storage, or exports. Do not include raw provider payloads, auth headers, or plaintext keys in user-visible errors.

## Cost Controls

Live provider calls are opt-in. Runs include a max-cost field and sample count limit. The first implementation estimates and displays cost but does not bill or meter provider-specific token prices precisely.
