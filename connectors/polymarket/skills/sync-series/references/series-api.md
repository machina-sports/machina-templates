# Polymarket Series API

Reference for browsing series (leagues/competitions) on Polymarket.

## What is a Series?

A series represents a league or competition that groups related events. For example, "NBA 2025-26" is a series containing all NBA game events for that season.

## Fetching Series

```python
# All series
mcp__docker-localhost__connector_executor(
    name="polymarket",
    command="get_series",
    payload={"limit": 200}
)
```

## Series Data Structure

Each synced series document contains:

```json
{
  "title": "NBA 2025-26",
  "slug": "nba-2025-26",
  "description": "NBA 2025-26 Regular Season",
  "image": "https://polymarket-upload.s3.us-east-2.amazonaws.com/nba.png",
  "createdAt": "2025-10-01T00:00:00Z",
  "updatedAt": "2026-02-15T00:00:00Z"
}
```

## Using Series to Filter Events

Get the series ID from synced documents, then use it to filter events:

```python
# 1. Find the NBA series
# Search polymarket-series documents for "NBA"

# 2. Use series_id to get NBA events only
mcp__docker-localhost__execute_workflow(
    name="polymarket-sync-events",
    input_data={"series_id": "<nba_series_id>", "limit": 100}
)
```

## Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | int | `100` | Max results (max 200) |
| `offset` | int | `0` | Pagination offset |

## Common Series

Sports series on Polymarket typically follow the pattern `{sport} {season}`:
- NBA 2025-26
- NFL 2025-26
- MLB 2026
- Premier League 2025-26
- Champions League 2025-26
- UFC / MMA
- Tennis Grand Slams
