# Polymarket Sports Market Types

Reference for the 58+ market types available on Polymarket sports.

## Common Market Types

| Type | Description | Example |
|------|-------------|---------|
| `moneyline` | Winner of the game | "Will the Lakers win?" |
| `spread` | Point spread | "Will the Chiefs cover -3.5?" |
| `total` | Over/under points | "Will the total go over 45.5?" |
| `player_points` | Player points prop | "Will LeBron score over 25.5?" |
| `player_rebounds` | Player rebounds prop | "Will Jokic get over 10.5 rebounds?" |
| `player_assists` | Player assists prop | "Will Trae Young get over 9.5 assists?" |
| `player_touchdowns` | Player TD prop | "Will Mahomes throw 3+ TDs?" |
| `player_passing_yards` | QB passing yards | "Will Burrow throw over 275.5 yards?" |
| `player_rushing_yards` | RB rushing yards | "Will Henry rush over 90.5 yards?" |
| `player_receiving_yards` | WR receiving yards | "Will Jefferson get over 85.5 yards?" |
| `first_scorer` | First to score | "Who will score first?" |
| `halftime_result` | Halftime winner | "Who leads at halftime?" |

## Filtering by Market Type

```python
# Sync only moneyline markets
mcp__docker-localhost__execute_workflow(
    name="polymarket-sync-markets",
    input_data={"sports_market_types": "moneyline", "limit": 100}
)

# Get all available market types
mcp__docker-localhost__connector_executor(
    name="polymarket",
    command="get_sports_market_types",
    payload={}
)
```

## Market Data Structure

Each synced market document contains:

```json
{
  "title": "Will the Lakers win vs Celtics?",
  "sportsMarketType": "moneyline",
  "gameId": "game_abc123",
  "outcomes": [
    {"name": "Yes", "price": 0.55, "clob_token_id": "tok_yes"},
    {"name": "No", "price": 0.45, "clob_token_id": "tok_no"}
  ],
  "volume": 150000.0,
  "volume24h": 25000.0,
  "liquidity": 80000.0,
  "spread": 0.02,
  "startDate": "2026-02-20T00:00:00Z",
  "endDate": "2026-02-21T00:00:00Z",
  "eventId": "evt_123",
  "tags": ["NBA", "Basketball"]
}
```

## Price Interpretation

- Prices are probabilities from 0.0 to 1.0
- Price 0.65 = 65% implied probability
- American odds conversion: `price > 0.5 → -(price/(1-price)*100)` else `+((1-price)/price*100)`
- Example: 0.65 → -186, 0.35 → +186
