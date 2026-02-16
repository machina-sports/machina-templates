# Polymarket Search

Reference for searching markets and events across Polymarket.

## Search Markets

Full-text search across event titles, descriptions, and slugs:

```python
mcp__docker-localhost__connector_executor(
    name="polymarket",
    command="search_markets",
    payload={
        "query": "nba",
        "limit": 20
    }
)

# Search with market type filter
mcp__docker-localhost__connector_executor(
    name="polymarket",
    command="search_markets",
    payload={
        "query": "chiefs",
        "sports_market_types": "moneyline",
        "limit": 10
    }
)
```

## Search Behavior

- Searches across event `title`, `description`, and `slug` fields
- Case-insensitive matching
- Returns markets from matching events (not events themselves)
- Results ordered by volume (highest first)
- Max 50 results per query

## Search Examples

| Query | Finds |
|-------|-------|
| `"nba"` | All NBA markets |
| `"chiefs"` | Kansas City Chiefs markets |
| `"lakers celtics"` | Won't match — search is single-term |
| `"lakers"` | All Lakers markets |
| `"super bowl"` | Super Bowl markets |
| `"messi"` | Player markets mentioning Messi |

## Tips

- Use specific team/player names for best results
- Combine with `sports_market_types` to narrow down (e.g., only moneyline)
- For browsing by league, use `get_sports_events` with `series_id` instead
- For browsing all market types, use `get_sports_market_types` first
