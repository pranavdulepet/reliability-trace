# API

Base URL: `http://localhost:8000`

## Health

`GET /health`

Returns service status, database path, and backend version.

## Providers

`GET /api/providers`

Returns supported provider metadata and whether each provider has a saved active key.

`GET /api/provider-preferences`

Returns saved chat defaults and the resolved provider when one is available.

`PUT /api/provider-preferences`

```json
{
  "provider": "openai",
  "model": "gpt-4.1-mini",
  "samples": 3,
  "max_cost_usd": 1.0
}
```

Stores default provider settings for new chat messages.

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
  "provider": "openai",
  "model": "gpt-4.1-mini",
  "samples": 3,
  "max_cost_usd": 1.0,
  "use_live_provider": true,
  "conversation_id": "conv_...",
  "attachment_document_ids": ["doc_..."]
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

## Conversations

`GET /api/conversations`

Lists chat threads.

`POST /api/conversations`

```json
{
  "title": "New chat"
}
```

Creates a thread.

`GET /api/conversations/{conversation_id}`

Returns a thread and messages. Assistant messages include the linked run graph when available.

`POST /api/conversations/{conversation_id}/messages`

```json
{
  "content": "Can I trust this answer?",
  "attachment_document_ids": ["doc_..."]
}
```

Creates a user message and queued reliability run. Stream `/api/runs/{run_id}/events` to complete the answer.

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

Stores source text, chunks it, builds local retrieval vectors, and returns a document id that can be attached to a chat message.

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
