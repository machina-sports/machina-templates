# Soccer Power Ranking

AI-powered team power ranking system for soccer leagues using fixture data and statistical performance analysis.

## Architecture

Uses the **unified `sport:Event` schema (IPTC)** for all fixture data, ensuring cross-system compatibility.

```
┌─────────────────────────────────────────────────────────────┐
│              Sync Layer (uses api-football-sync-fixtures)   │
├─────────────────────────────────────────────────────────────┤
│  sync-league-fixtures (Agent)                               │
│     └── api-football-sync-fixtures (Workflow)               │
│            ├── API Football GET /fixtures                   │
│            ├── IPTC Event Mapping                           │
│            └── Save 380 docs (sport:Event)                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              Document DB (380 sport:Event per season)       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                    │
│  │sport:Evt │ │sport:Evt │ │sport:Evt │ ...                │
│  │IPTC schem│ │IPTC schem│ │IPTC schem│                    │
│  │competitors│ │competitors│ │competitors│                  │
│  └──────────┘ └──────────┘ └──────────┘                    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              Ranking Layer (N simulations, 0 API calls)     │
├─────────────────────────────────────────────────────────────┤
│  soccer-power-ranking-progressive (Agent)                   │
│     ├── get-league-teams (1x)                               │
│     ├── calculate-team-metrics (foreach team)               │
│     │      ├── filter sport:Event by team URN               │
│     │      └── save team-progressive-metrics                │
│     └── aggregate-rankings (1x)                             │
│            └── normalize & rank                             │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Install Template

```python
mcp_machina-client-dev_get_local_template(
    template="agent-templates/soccer-power-ranking",
    project_path="/app/machina-templates/agent-templates/soccer-power-ranking"
)
```

### 2. Sync Fixtures (once per season)

```python
# Get sync agent ID
agent = mcp_machina-client-dev_get_agent_by_name(name="soccer-power-ranking-sync-fixtures")
sync_agent_id = agent["data"]["data"]["_id"]

# Sync Brasileirão 2025
mcp_machina-client-dev_execute_agent(
    agent_id=sync_agent_id,
    messages=[],
    context={"league_id": "71", "season": "2025"}
)
```

### 3. Calculate Rankings (unlimited simulations)

```python
# Get progressive agent ID
agent = mcp_machina-client-dev_get_agent_by_name(name="soccer-power-ranking-progressive")
ranking_agent_id = agent["data"]["data"]["_id"]

# Calculate rankings for a specific date
mcp_machina-client-dev_execute_agent(
    agent_id=ranking_agent_id,
    messages=[],
    context={
        "league_id": "71",
        "date": "2025-04-15",
        "last_matches": 10
    }
)
```

## Agents

| Agent | Purpose |
|-------|---------|
| `soccer-power-ranking-sync-fixtures` | Sync fixtures to sport:Event documents (IPTC schema) |
| `soccer-power-ranking-progressive` | Calculate power rankings using local fixture data |

## Workflows

| Workflow | Purpose |
|----------|---------|
| `sync-league-fixtures` | Delegates to api-football-sync-fixtures for IPTC sport:Event storage |
| `get-league-teams` | Get all teams from a league |
| `calculate-team-metrics` | Calculate metrics for a single team from sport:Event documents |
| `aggregate-rankings` | Normalize and rank all teams |

## Document Types

| Document | Schema | Purpose |
|----------|--------|---------|
| `sport:Event` | IPTC | Individual match data (unified across systems) |
| `team-progressive-metrics` | Custom | Per-team metrics snapshot with considered fixtures |
| `power-rankings-progressive` | Custom | Final aggregated rankings |

## Parameters

### Sync Agent

| Parameter | Required | Description |
|-----------|----------|-------------|
| `league_id` | Yes | API Football league ID (e.g., "71" for Brasileirão) |
| `season` | Yes | Season year (e.g., "2025") |

### Ranking Agent

| Parameter | Required | Description |
|-----------|----------|-------------|
| `league_id` | Yes | API Football league ID |
| `season` | No | Season year (derived from date if not provided) |
| `date` | No | Reference date "YYYY-MM-DD" for point-in-time rankings |
| `last_matches` | No | Number of recent matches to consider (default: 10) |

## Power Ranking Methodology

### Scoring Formula (Progressive Mode)

```
Power Score = 45% × Outcome + 30% × Attack + 25% × Defense
```

**Note**: Discipline score is not available in progressive mode (fixture data doesn't include cards).

### Pillars

| Pillar | Weight | Components |
|--------|--------|------------|
| **Outcome** | 45% | Win rate (60%) + Points per game (40%) |
| **Attack** | 30% | Goals per game (70%) + Scoring rate (30%) |
| **Defense** | 25% | Concede rate inverted (60%) + Clean sheet rate (40%) |

### Normalization

All metrics are normalized using **Min-Max normalization** across all teams:

```python
normalized = (value - min) / (max - min)
```

This ensures fair comparison regardless of league characteristics.

## sport:Event Schema (IPTC)

The template uses the unified IPTC sport:Event schema:

```json
{
  "@id": "urn:apifootball:sport_event:1378969",
  "name": "Liverpool vs Bournemouth - Premier League",
  "schema:startDate": "2025-08-15T19:00:00+00:00",
  "sport:competition": {
    "@id": "urn:apifootball:league:39",
    "name": "Premier League"
  },
  "sport:competitors": [
    {
      "@id": "urn:apifootball:team:40",
      "name": "Liverpool",
      "sport:qualifier": "home"
    },
    {
      "@id": "urn:apifootball:team:35",
      "name": "Bournemouth",
      "sport:qualifier": "away"
    }
  ],
  "sport:score": {
    "sport:homeScore": 4,
    "sport:awayScore": 2
  },
  "sport:status": "FT"
}
```

## Example Output

```json
{
  "rankings": [
    {
      "rank": 1,
      "team_id": "127",
      "team_name": "Flamengo",
      "power_score": 0.7733,
      "breakdown": {
        "outcome_score": 0.7111,
        "attack_score": 1.0,
        "defense_score": 0.6133,
        "discipline_score": null
      },
      "metrics": {
        "games": 3,
        "wins": 2,
        "draws": 1,
        "losses": 0,
        "goals_for": 5,
        "goals_against": 2,
        "win_rate": 0.6667,
        "points_per_game": 2.33
      }
    }
  ],
  "league_stats": {
    "total_teams": 20,
    "avg_power_score": 0.4549
  }
}
```

## Benefits

1. **Unified Schema**: Uses sport:Event (IPTC) for cross-system compatibility
2. **Cost Efficient**: Sync once, simulate unlimited times (0 API calls)
3. **Fast**: No network latency during ranking calculations
4. **Flexible**: Filter by any date without API restrictions
5. **Accurate**: Individual team processing prevents cross-contamination

## Supported Leagues

Any league supported by API Football. Common examples:

| League | ID |
|--------|-----|
| Brasileirão (Brazil) | 71 |
| Premier League (England) | 39 |
| La Liga (Spain) | 140 |
| Serie A (Italy) | 135 |
| Bundesliga (Germany) | 78 |
| Ligue 1 (France) | 61 |
