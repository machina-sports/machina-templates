---
name: polymarket-sync-series
description: Sync series (leagues/competitions) from Polymarket. Use when users ask to "sync polymarket series", "fetch leagues", "import polymarket leagues", or "get prediction market competitions". Fetches series data, maps to documents, and stores with embeddings.
---

# Polymarket - Sync Series

Syncs series (leagues/competitions) from Polymarket Gamma API into `polymarket-series` documents with vector embeddings.

## Workflow

**Name**: `polymarket-sync-series`

| Input | Default | Description |
|-------|---------|-------------|
| `limit` | `200` | Max series to fetch |
| `offset` | `0` | Pagination offset |

## Usage

```python
# Sync all series
mcp__docker-localhost__execute_workflow(name="polymarket-sync-series")

# Sync with pagination
mcp__docker-localhost__execute_workflow(
    name="polymarket-sync-series",
    input_data={"limit": 200, "offset": 0}
)
```

## Pipeline

```
get_series → polymarket-series-mapping → bulk-save (polymarket-series)
```

## Dependencies

- **polymarket** connector (no auth required)
- **machina-ai** connector (for embeddings) — requires `$TEMP_CONTEXT_VARIABLE_SDK_OPENAI_API_KEY`
