# Tallysight API Connector

Connect to the Tallysight API to access sports betting widgets, odds, and market data across multiple leagues, teams, and players.

## Features

- Bet Finder Widgets
- Odds Text Widgets
- Futures Tiles
- Gamelines Tiles
- Props Tiles
- League Data
- Team & Player Props
- Workspace Management

## Authentication

The connector requires a Tallysight API key stored as:
```
TEMP_CONTEXT_VARIABLE_TALLYSIGHT_API_KEY
```

## Sportsbook Parameter

**IMPORTANT**: When using the `sportsbooks` parameter, use the correct slug format with hyphens:

### Correct Format ✅
```yaml
inputs:
  sportsbooks: "'sports-interaction'"  # String value with hyphen
```

### Common Sportsbook Slugs
- `sports-interaction` - Sports Interaction
- `sportingbet` - Sportingbet

**Note**: The `sportsbooks` parameter must be passed as a **string value** in the `inputs` section, not in `command_attribute`.

## Available Endpoints

### Core Endpoints (No Parameters Required)

1. **Get Workspaces** - `/api/v2/workspaces`
   - Returns list of available workspaces
   - No parameters required

2. **Get Brands** - `/api/v2/brands`
   - Returns list of brands
   - No parameters required

3. **Get Leagues** - `/api/v2/leagues`
   - Returns list of available leagues
   - No parameters required

### Bet Finder Widgets

4. **Player Bet Finder** - `/api/v2/widgets/bet-finder/leagues/{league}/players/{player}`
   - Required parameters: `league`, `player`, `sportsbooks`

5. **Team Bet Finder** - `/api/v2/widgets/bet-finder/leagues/{league}/teams/{team}`
   - Required parameters: `league`, `team`, `sportsbooks`

### Odds Text Widgets

6. **Gamelines Odds Text** - `/api/v2/widgets/odds-text/gamelines/leagues/{league}/matchup/{team1}/{team2}/{date}`
   - Required parameters: `league`, `team1`, `team2`, `date`, `sportsbooks`

### Futures Tiles

7. **Player Futures** - `/api/v2/widgets/tiles/futures/leagues/{league}/players/{player}`
   - Required parameters: `league`, `player`
   - Optional: `variant`, `sportsbook`

8. **Team Futures** - `/api/v2/widgets/tiles/futures/leagues/{league}/teams/{team}`
   - Required parameters: `league`, `team`
   - Optional: `variant`, `sportsbook`

### Gamelines Tiles

9. **Gamelines Tiles** - `/api/v2/widgets/tiles/gamelines/leagues/{league}/matchup/{team1}/{team2}/{date}`
   - Required parameters: `league`, `team1`, `team2`, `date`
   - Optional: `variant`, `sportsbook`

### Props Tiles

10. **Matchup Props** - `/api/v2/widgets/tiles/props/leagues/{league}/matchup/{team1}/{team2}/{date}`
    - Required parameters: `league`, `team1`, `team2`, `date`
    - Optional: `variant`, `sportsbook`

11. **Player Props** - `/api/v2/widgets/tiles/props/leagues/{league}/players/{player}`
    - Required parameters: `league`, `player`
    - Optional: `variant`, `sportsbook`

12. **Team Props** - `/api/v2/widgets/tiles/props/leagues/{league}/teams/{team}`
    - Required parameters: `league`, `team`
    - Optional: `variant`, `sportsbook`

## Example Workflows

### Basic Connection Test

```yaml
workflow:
  name: "tallysight-test-connection"
  context-variables:
    tallysight:
      key: "$TEMP_CONTEXT_VARIABLE_TALLYSIGHT_API_KEY"

  tasks:
    - type: "connector"
      name: "get-leagues"
      connector:
        name: "tallysight"
        command: "get-api/v2/leagues"
      outputs:
        leagues: "$"
```

### Player Bet Finder with Correct Sportsbooks Parameter

```yaml
workflow:
  name: "tallysight-player-bets"
  context-variables:
    tallysight:
      key: "$TEMP_CONTEXT_VARIABLE_TALLYSIGHT_API_KEY"
  inputs:
    league: "$.get('league', 'nfl')"
    player: "$.get('player', 'josh-allen')"

  tasks:
    - type: "connector"
      name: "get-player-bets"
      connector:
        name: "tallysight"
        command: "get-api/v2/widgets/bet-finder/leagues/{league}/players/{player}"
        command_attribute:
          league: "$.get('league')"
          player: "$.get('player')"
      inputs:
        sportsbooks: "'sports-interaction'"  # ✅ Query parameter as string
        embed: "'wordpress'"
        format: "'decimal'"
        locale: "'en'"
      outputs:
        widget: "$"
```

## Testing

Use the included `test-connection.yml` workflow to validate your API key:

```bash
# Via MCP
mcp__sportsinteraction_dev__execute_workflow(
    name="tallysight-test-connection",
    context={}
)
```

Expected output:
- ✅ Workspaces list
- ✅ Brands list
- ✅ Leagues list (19 leagues for Sports Interaction workspace)

## Troubleshooting

### Invalid Sportsbook Parameter

**Problem**: API returns empty results or errors, or "Path attribute 'sportsbooks' not found"

**Solution**: Ensure sportsbooks parameter uses correct format:
- ❌ Wrong: `command_attribute: { sportsbooks: ["sports-interaction"] }`
- ❌ Wrong: `inputs: { sportsbooks: ["sportsinteraction"] }`
- ✅ Correct: `inputs: { sportsbooks: "'sports-interaction'" }`

**Key points**:
1. Must be in `inputs` section, NOT `command_attribute`
2. Must use hyphenated slug: `sports-interaction` not `sportsinteraction`
3. Must be a string value: `"'sports-interaction'"` not an array

### Missing API Key

**Problem**: 401 Unauthorized errors

**Solution**: Verify the secret exists:
```python
mcp__sportsinteraction_dev__check_secrets(
    name="TEMP_CONTEXT_VARIABLE_TALLYSIGHT_API_KEY"
)
```

## Version

- **Version**: 1.0.0
- **Status**: Available
- **Category**: Data Acquisition, Sports Betting, Odds Widgets
