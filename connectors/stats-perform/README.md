# Stats Perform Opta Connector

This connector provides integration with the Stats Perform Opta Soccer API, enabling you to fetch competitions, seasons, schedules, and match data.

## Overview

The Stats Perform Opta API provides comprehensive soccer data including:
- Tournament Calendars (Competitions and Seasons)
- Match Schedules and Fixtures
- Live Match Data
- Player Statistics
- Team Information
- And much more...

## Prerequisites

Before using this connector, you need:

1. **Opta Outlet ID** - Your unique outlet authentication key
2. **Opta Secret** - Your API secret for OAuth authentication

Set these as environment variables:
- `MACHINA_CONTEXT_VARIABLE_OPTA_OUTLET`
- `MACHINA_CONTEXT_VARIABLE_OPTA_SECRET`

## Components

### Connector (`opta.yml`)

The base connector with two main commands:
- `authorization` - Get OAuth access token
- `invoke_request` - Make authenticated API requests

### Workflows

#### 1. **invoke-request.yml** (`sp-opta-invoke-request`)
Basic workflow to invoke any Opta API endpoint.

**Inputs:**
- `competition_id` (optional): Competition ID
- `endpoint` (default: 'tournamentcalendar'): API endpoint name
- `query_params` (optional): Additional query parameters

**Example Usage:**
```yaml
inputs:
  competition_id: "2kwbbcootiqqgmrzs6o5inle5"  # Premier League
  endpoint: "tournamentcalendar"
  query_params: {}
```

#### 2. **sync-competitions.yml** (`sp-opta-sync-competitions`)
Synchronize all tournament calendars (competitions) to Machina documents.

**Features:**
- Checks for expired data (7-day cache)
- Fetches all competitions from Opta
- Saves to document store for querying

**Outputs:**
- `competitions`: Array of competition objects
- `workflow-status`: 'executed' or 'skipped'

#### 3. **sync-seasons.yml** (`sp-opta-sync-seasons`)
Synchronize seasons for a specific competition.

**Inputs:**
- `competition_id` (required): The competition ID

**Features:**
- Checks for expired data (7-day cache)
- Fetches seasons for specified competition
- Links to competition document
- Saves individual season documents

**Outputs:**
- `seasons`: Array of season objects
- `workflow-status`: 'executed' or 'skipped'

#### 4. **sync-schedules.yml** (`sp-opta-sync-schedules`)
Synchronize match schedules for a competition/season.

**Inputs:**
- `competition_id` (required): The competition ID
- `season_id` (optional): Specific season ID to filter

**Features:**
- Fetches match schedules from Tournament Schedule endpoint
- Creates standardized `sport:Event` documents
- De-duplicates existing events
- Supports semantic search via embeddings

**Outputs:**
- `schedules`: Array of match objects
- `workflow-status`: 'executed' or 'skipped'

#### 5. **sync-standings.yml** (`sp-opta-sync-standings`)
Synchronize team standings (league table/classificação).

**Inputs:**
- `tournament_calendar_id` (required): The season/tournament calendar ID

**Features:**
- Checks for expired data (6-hour cache)
- Fetches complete league table with:
  - Team position, points, games played
  - Wins, draws, losses
  - Goals scored, conceded, and goal difference
  - All division types (total, home, away, form, etc.)
- Links to season document
- Saves aggregated standings and individual team standings

**Outputs:**
- `standings`: Complete league table data
- `workflow-status`: 'executed' or 'skipped'

**Note:** Returns ALL division types (total, home, away, form, etc.) in a single call.

#### 6. **sync-match-stats.yml** (`sp-opta-sync-match-stats`)
Synchronize detailed match statistics.

**Inputs:**
- `match_id` (required): The match/fixture UUID

**Features:**
- Checks for expired data (24-hour cache)
- Fetches detailed match statistics including:
  - Match info (teams, venue, competition, etc.)
  - Live data (match details, periods, lineups)
  - Team statistics (formation, aggregated stats)
  - Individual player statistics (passes, shots, tackles, etc.)
- Saves 3 types of documents:
  - Complete match data (1 doc)
  - Team statistics per match (2 docs - one per team)
  - Player statistics per match (~46 docs - all players)

**Outputs:**
- `match_stats`: Complete match statistics data
- `workflow-status`: 'executed' or 'skipped'

**Note:** Requires match_id (fixture UUID). Use `sync-schedules` first to get match IDs.

#### 7. **sync-match-xg.yml** (`sp-opta-sync-match-xg`)
Synchronize match expected goals (xG) data.

**Inputs:**
- `match_id` (required): The match/fixture UUID

**Features:**
- Checks for expired data (24-hour cache)
- Fetches expected goals (xG) data from stat arrays:
  - Team statistics: `expectedGoals`, `expectedGoalsontarget`, `expectedGoalsNonpenalty`
  - Player statistics: Same stat types per player
  - Shot events: Individual shots (typeId=13) with qualifiers
- Saves 4 types of documents:
  - Complete match xG data (1 doc)
  - Team xG statistics per match (2 docs - one per team)
  - Player xG statistics per match (players with xG stats)
  - Shot events with xG (all shots in the match)

**Outputs:**
- `match_xg`: Complete match expected goals data
- `workflow-status`: 'executed' or 'skipped'

**Note:** xG data comes in `stat` arrays with types like 'expectedGoals', 'expectedGoalsontarget'. Shot events (typeId=13) contain detailed xG in qualifiers.

#### 8. **sync-transfers.yml** (`sp-opta-sync-transfers`)
Synchronize player transfer data.

**Inputs:**
- `contestant_id` (required): Team/contestant ID
- `competition_id` (optional): Competition ID
- `strt_dt` (optional): Start date for transfers
- `end_dt` (optional): End date for transfers

**Features:**
- Fetches player transfer information
- Supports date range filtering

**Outputs:**
- `transfers`: Array of transfer objects
- `transfers_raw`: Raw API response
- `workflow-status`: 'executed'

### Agent (`agents/sp-opta-sync.yml`)

**Agent Name:** `sp-opta-sync-agent`

Orchestrates multiple sync operations in sequence:
1. Sync all competitions
2. Sync seasons for a competition (if `competition_id` provided)
3. Sync schedules for a competition/season (if `competition_id` provided)

**Context Inputs:**
- `competition_id`: Optional competition to sync
- `season_id`: Optional season to filter schedules

## Usage Examples

### Example 1: Test Basic API Connection

```yaml
workflow:
  name: test-connection
  tasks:
    - type: workflow
      workflow:
        name: sp-opta-invoke-request
      inputs:
        endpoint: "tournamentcalendar"
        competition_id: "2kwbbcootiqqgmrzs6o5inle5"
```

### Example 2: Sync Premier League Data

```yaml
workflow:
  name: sync-premier-league
  inputs:
    competition_id: "2kwbbcootiqqgmrzs6o5inle5"  # Premier League
  tasks:
    - type: workflow
      workflow:
        name: sp-opta-sync-seasons
      inputs:
        competition_id: $.get('competition_id')
    
    - type: workflow
      workflow:
        name: sp-opta-sync-schedules
      inputs:
        competition_id: $.get('competition_id')
```

### Example 3: Get Team Standings (League Table)

```yaml
workflow:
  name: get-standings
  inputs:
    tournament_calendar_id: "9pqtmpr3w8jm73y0eb8hmum8k"  # Season ID from sync-seasons
  tasks:
    - type: workflow
      workflow:
        name: sp-opta-sync-standings
      inputs:
        tournament_calendar_id: $.get('tournament_calendar_id')
```

### Example 4: Get Match Statistics

```yaml
workflow:
  name: get-match-stats
  inputs:
    match_id: "abc123xyz"  # Match ID from sync-schedules
  tasks:
    - type: workflow
      workflow:
        name: sp-opta-sync-match-stats
      inputs:
        match_id: $.get('match_id')
```

### Example 5: Get Match Expected Goals (xG)

```yaml
workflow:
  name: get-match-xg
  inputs:
    match_id: "abc123xyz"  # Match ID from sync-schedules
  tasks:
    - type: workflow
      workflow:
        name: sp-opta-sync-match-xg
      inputs:
        match_id: $.get('match_id')
```

### Example 6: Use the Sync Agent

Execute the agent using the Machina API:

```python
from machina import execute_agent

result = execute_agent(
    agent_id="sp-opta-sync-agent",
    messages=[
        {
            "role": "user",
            "content": {
                "competition_id": "2kwbbcootiqqgmrzs6o5inle5"  # Premier League
            }
        }
    ]
)
```

## API Endpoints Reference

Common Opta Soccer API endpoints you can use with `invoke-request`:

| Endpoint | Description | Common Parameters |
|----------|-------------|-------------------|
| `tournamentcalendar` | Tournament calendars and seasons | `comp={competition_id}` |
| `tournamentschedule` | Match schedules | `comp={competition_id}`, `seasonId={season_id}` |
| `match` | Fixtures and results | `comp={competition_id}` |
| `matchstats` | Match statistics (detailed) | `matchId={match_id}` |
| `matchexpectedgoals` | Match expected goals (xG, xGOT) | `matchId={match_id}` |
| `matchevent` | Match events | `matchId={match_id}` |
| `standings` | Team standings (league table) | `tmcl={tournament_calendar_id}` |
| `squads` | Team squads | `tmcl={team_id}` |

For a complete list, see the [Stats Perform Opta API Documentation](https://developer.statsperform.com/).

## Common Competition IDs

| Competition | ID |
|-------------|-----|
| Premier League | `2kwbbcootiqqgmrzs6o5inle5` |
| La Liga | `34pl8szyvrbwcmfkuocjm3r6t` |
| Bundesliga | `6by3h89i2eykc341oz7lv1ddd` |
| Serie A | `1r097lpxe0xn03ihb7wi98kao` |
| Ligue 1 | `dm5ka0os1e3dxcp3vh05kmp33` |

## Document Types

The sync workflows create the following document types:

- `sp-competition`: Individual competition/tournament
- `sp-season`: Individual season within a competition
- `sp-team`: Team/contestant information
- `sport:Event`: Match/fixture events (standardized format)
- `sp-standings`: Aggregated league table/standings data
- `sp-team-standing`: Individual team standing/position in league table
- `sp-match-stats`: Complete match data (match info + live data)
- `sp-team-match-stats`: Team statistics for a match (formation, aggregated stats)
- `sp-player-match-stats`: Individual player statistics for a match
- `sp-match-xg`: Complete match expected goals data
- `sp-team-match-xg`: Team xG statistics (expectedGoals, expectedGoalsontarget, stats array)
- `sp-player-match-xg`: Player xG statistics (expectedGoals, expectedGoalsontarget per player)
- `sp-shot-event-xg`: Individual shot events with xG values from qualifiers
- `synchronization`: Metadata documents for sync tracking

## Authentication Flow

1. The `authorization` command generates an OAuth token using:
   - Outlet ID
   - Secret
   - Timestamp
   - SHA512 hash
2. Token is valid for the session
3. All subsequent requests use `Bearer {token}` authentication

## Error Handling

All workflows include:
- Token expiration handling
- API rate limit awareness
- Data validation
- Graceful skipping when data is cached

## Version

Current version: `0.2.0`

## Support

For issues or questions:
1. Check the [Stats Perform Developer Portal](https://developer.statsperform.com/)
2. Review the API documentation
3. Contact your Stats Perform account manager

## License

This connector is part of the Machina Templates repository.

