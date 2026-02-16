# Polymarket Events API

Reference for browsing and syncing sports events from Polymarket.

## What is an Event?

An event groups related markets for a single game or match. For example, "Lakers vs Celtics" is an event that contains markets like moneyline, spread, total, and player props.

## Fetching Events

```python
# All active sports events
mcp__docker-localhost__connector_executor(
    name="polymarket",
    command="get_sports_events",
    payload={"tag_id": 1, "limit": 50}
)

# Events from a specific series/league
mcp__docker-localhost__connector_executor(
    name="polymarket",
    command="get_sports_events",
    payload={"series_id": "<series_id>", "limit": 50}
)

# Single event by ID
mcp__docker-localhost__connector_executor(
    name="polymarket",
    command="get_event_details",
    payload={"event_id": "<event_id>"}
)

# Single event by slug
mcp__docker-localhost__connector_executor(
    name="polymarket",
    command="get_event_details",
    payload={"slug": "lakers-vs-celtics"}
)
```

## Event Data Structure

Each synced event document contains:

```json
{
  "title": "Lakers vs Celtics",
  "description": "NBA regular season game",
  "slug": "lakers-vs-celtics-feb-20",
  "status": "active",
  "startDate": "2026-02-20T00:00:00Z",
  "endDate": "2026-02-21T00:00:00Z",
  "volume": 500000.0,
  "liquidity": 200000.0,
  "marketCount": 12,
  "seriesId": "nba-2025-26",
  "tags": ["NBA", "Basketball"]
}
```

## Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `tag_id` | int | `1` | Tag filter (1 = Sports) |
| `series_id` | string | `""` | Filter by series/league |
| `limit` | int | `50` | Max results (max 100) |
| `offset` | int | `0` | Pagination offset |
| `active` | bool | `true` | Only active events |
| `closed` | bool | `false` | Include closed events |
| `order` | string | `"volume"` | Sort field |
| `ascending` | bool | `false` | Sort direction |

## Event → Markets Relationship

Events contain embedded markets. When fetching event details, all associated markets are returned with current prices. Use `event_id` in market data to cross-reference.
