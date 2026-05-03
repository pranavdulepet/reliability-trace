# API

Base URL: `http://localhost:8000`

## Health

`GET /health`

Returns service status, database path, and backend version.

## Providers

`GET /api/providers`

Returns supported provider metadata and whether each provider has a saved active key.

## Keys

`GET /api/keys`

Lists encrypted saved key fingerprints.

`POST /api/keys`

```json
{
  "provider": "tinker",
  "api_key": "tk-..."
}
```

`DELETE /api/keys/{provider}`

Deletes the saved local key for the current user.

## Runs

`POST /api/runs`

```json
{
  "question": "Should I build this product?",
  "provider": "tinker",
  "model": "tinker://.../sampler_weights/000080",
  "samples": 3,
  "max_cost_usd": 1.0,
  "use_live_provider": false
}
```

`GET /api/runs/{run_id}/events`

Streams Server-Sent Events. The final event includes the graph.

`GET /api/runs/{run_id}`

Returns the persisted graph after completion.

`GET /api/runs/{run_id}/export`

Downloads the full Reliability Evidence Graph JSON.

`POST /api/runs/{run_id}/label`

Stores a local user label for later calibration research.

## Documents

`GET /api/documents`

Lists indexed documents and fetched source pages.

`POST /api/documents`

```json
{
  "title": "Source notes",
  "text": "Long source text...",
  "source_url": "https://example.com/source",
  "source_type": "uploaded_document"
}
```

Stores source text, chunks it, builds local retrieval vectors, and makes it available for later claim matching.

`POST /api/documents/fetch`

```json
{
  "url": "https://example.com/source"
}
```

Fetches an HTTP(S) page, extracts text, chunks it, and indexes it as a source.

`GET /api/documents/search?q=claim`

Returns the highest-ranked source chunks for a query.

## Benchmarks

`GET /api/benchmarks/report`

Builds the current local calibration and ablation report from labeled completed runs.
