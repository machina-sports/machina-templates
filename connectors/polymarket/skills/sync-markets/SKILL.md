---
name: polymarket-sync-markets
description: Sync sports prediction markets from Polymarket. Use when users ask to "sync polymarket markets", "fetch prediction markets", "get sports odds", or "import polymarket market data". Fetches active markets with prices, maps to documents, and stores with embeddings.
---

# Polymarket - Sync Markets

Syncs active sports prediction markets from Polymarket Gamma API into `polymarket-markets` documents with vector embeddings.

## Workflow

**Name**: `polymarket-sync-markets`

| Input | Default | Description |
|-------|---------|-------------|
| `tag_id` | `1` (Sports) | Polymarket tag filter |
| `sports_market_types` | `""` (all) | Filter by type (moneyline, spread, total, etc.) |
| `limit` | `100` | Max markets to fetch |
| `offset` | `0` | Pagination offset |

## Usage

```python
# Sync all sports markets
mcp__docker-localhost__execute_workflow(
    name="polymarket-sync-markets",
    input_data={"tag_id": 1, "limit": 100}
)

# Sync only moneyline markets
mcp__docker-localhost__execute_workflow(
    name="polymarket-sync-markets",
    input_data={"sports_market_types": "moneyline", "limit": 50}
)
```

## Pipeline

```
get_sports_markets → polymarket-market-mapping → bulk-save (polymarket-markets)
```

## Dependencies

- **polymarket** connector (no auth required)
- **machina-ai** connector (for embeddings) — requires `$TEMP_CONTEXT_VARIABLE_SDK_OPENAI_API_KEY`
