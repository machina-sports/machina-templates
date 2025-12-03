# Kalshi Market Agent - Sports Markets

This agent template provides workflows for monitoring and analyzing sports-related prediction markets from Kalshi.

## Overview

Based on analysis of the Kalshi API, we found:
- **897 series** in the "Sports" category
- **1,114 sports-related series** total (including cross-category matches)
- **5 sports event tickers** identified
- **20+ sports markets** found across various statuses (active, closed, finalized)

## Workflows

### 1. `sync-sports-markets.yml`
**Purpose:** Synchronize sports-related markets from Kalshi API to Machina documents.

**Key Features:**
- Filters markets using sports keywords (nfl, nba, mlb, nhl, soccer, football, basketball, etc.)
- Filters by category='Sports'
- Supports filtering by `event_ticker`, `series_ticker`, and `status`
- Saves to `kalshi-sports-market` document collection
- Generates embeddings for searchability

**Usage:**
```yaml
inputs:
  status: "open"  # Filter by market status
  limit: 500      # Number of markets to fetch
  event_ticker: "KXNYKCOACH-25"  # Optional: filter by event
  series_ticker: "KXNBATEAM"     # Optional: filter by series
```

**Outputs:**
- `sports_markets_synced`: Number of markets synced
- `total_markets_found`: Total markets found before filtering

### 2. `sync-sports-events.yml`
**Purpose:** Synchronize sports-related events from Kalshi API.

**Key Features:**
- Filters events using sports keywords
- Filters by category='Sports'
- Saves to `kalshi-sports-event` document collection
- Supports pagination with cursor

**Usage:**
```yaml
inputs:
  limit: 200
  status: "open"
  series_ticker: "KXNBATEAM"  # Optional: filter by series
```

### 3. `analyze-sports-markets.yml`
**Purpose:** Analyze active sports markets using AI to identify trends and opportunities.

**Key Features:**
- Fetches active sports markets
- Filters by minimum volume threshold
- Uses Gemini AI to analyze:
  - Implied probabilities from Yes/No prices
  - Volume trends and money flow
  - Market sentiment
  - Anomalies and opportunities
- Provides sports context-aware analysis

**Usage:**
```yaml
inputs:
  limit: 50
  status: "open"
  min_volume: 0  # Minimum volume threshold
  event_ticker: "KXNYKCOACH-25"  # Optional
```

**Outputs:**
- `analysis`: AI-generated market analysis (markdown)
- `markets_analyzed`: Number of markets analyzed
- `sports_markets_found`: Number of sports markets found

### 4. `monitor-active-sports-markets.yml`
**Purpose:** Monitor active sports markets and identify high-volume or trending opportunities.

**Key Features:**
- Identifies high-volume markets (configurable threshold)
- Identifies trending markets (high 24h volume)
- Saves active markets to `kalshi-active-sports-market` collection
- Tracks volume, liquidity, and open interest

**Usage:**
```yaml
inputs:
  limit: 500
  min_volume: 1000      # Minimum volume threshold
  min_liquidity: 500   # Minimum liquidity threshold
```

**Outputs:**
- `active_sports_markets`: List of all active sports markets
- `high_volume_markets`: Markets with volume >= min_volume
- `trending_markets`: Top 20 markets by 24h volume

### 5. `analyze-market.yml` (Legacy)
**Purpose:** Analyze a specific market series (original workflow).

**Usage:**
```yaml
inputs:
  series_ticker: "KXHIGHNY"
  limit: 10
```

## Sports Keywords Detected

The workflows automatically filter for markets/events containing these keywords:
- **Sports:** sport, nfl, nba, mlb, nhl, soccer, football, basketball, baseball, hockey
- **Other Sports:** tennis, golf, boxing, mma, ufc, nascar, f1, formula, racing, cricket, rugby
- **Events:** olympics, olympic, game, match, team, player, coach, draft, playoff, championship
- **Championships:** super bowl, world cup, stanley cup, world series, nba finals, nfl playoffs
- **College:** college football, college basketball, ncaa

## Recommended Workflow Strategy

### Initial Setup
1. **Sync Sports Events** (`sync-sports-events.yml`)
   - Run with `limit: 200` to get all sports events
   - This identifies event tickers for filtering

2. **Sync Sports Markets** (`sync-sports-markets.yml`)
   - Run with `status: "open"` to get active markets
   - Use `limit: 500` to get comprehensive coverage
   - Optionally filter by specific `event_ticker` values

### Continuous Monitoring
1. **Monitor Active Markets** (`monitor-active-sports-markets.yml`)
   - Run periodically (every hour/day)
   - Identifies high-volume and trending markets
   - Updates `kalshi-active-sports-market` collection

2. **Analyze Sports Markets** (`analyze-sports-markets.yml`)
   - Run on schedule or trigger
   - Provides AI-powered insights
   - Focus on markets with `min_volume > 0` for meaningful analysis

### Event-Specific Analysis
- Use `event_ticker` filters for specific sports events:
  - `KXNYKCOACH-25`: New York Pro Men's Basketball coach
  - `KXCANADACUP-30`: Canadian Stanley Cup winner
  - `KXSPORTSOWNERLBJ-30`: LeBron James team ownership
  - `KXNBATEAM-30`: NBA new team expansion
  - `KXNBASEATTLE-30`: Seattle pro basketball team

## Document Collections

- `kalshi-sports-market`: All sports markets (synced)
- `kalshi-sports-event`: All sports events (synced)
- `kalshi-active-sports-market`: Currently active sports markets (monitored)

## Integration with Findings

Based on `sports_findings.json`:
- **897 series** in "Sports" category - use `category='Sports'` filter
- **5 event tickers** identified - use for targeted analysis
- **Mix of statuses**: initialized, active, finalized, closed
- Focus on `status='open'` for active trading opportunities

## Next Steps

1. Configure agent with appropriate schedule
2. Set up monitoring for active markets
3. Use event tickers for targeted analysis
4. Review AI analysis outputs for insights
5. Adjust volume/liquidity thresholds based on needs

