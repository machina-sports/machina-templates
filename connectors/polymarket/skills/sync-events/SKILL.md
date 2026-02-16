---
name: polymarket-sync-events
description: Sync sports events from Polymarket. Use when users ask to "sync polymarket events", "fetch sports events", "import polymarket event data", or "get prediction market events". Fetches active events with embedded markets, maps to documents, and stores with embeddings.
---

# Polymarket - Sync Events

Syncs active sports events from Polymarket Gamma API into `polymarket-events` documents with vector embeddings.

## Workflow

**Name**: `polymarket-sync-events`

| Input | Default | Description |
|-------|---------|-------------|
| `tag_id` | `1` (Sports) | Polymarket tag filter |
| `series_id` | `""` (all) | Filter by series/league |
| `limit` | `100` | Max events to fetch |
| `offset` | `0` | Pagination offset |

## Usage

```python
# Sync all sports events
mcp__docker-localhost__execute_workflow(
    name="polymarket-sync-events",
    input_data={"tag_id": 1, "limit": 100}
)

# Sync events from a specific series/league
mcp__docker-localhost__execute_workflow(
    name="polymarket-sync-events",
    input_data={"series_id": "<series_id>", "limit": 50}
)
```

## Pipeline

```
get_sports_events → polymarket-event-mapping → bulk-save (polymarket-events)
```

## Dependencies

- **polymarket** connector (no auth required)
- **machina-ai** connector (for embeddings) — requires `$TEMP_CONTEXT_VARIABLE_SDK_OPENAI_API_KEY`
