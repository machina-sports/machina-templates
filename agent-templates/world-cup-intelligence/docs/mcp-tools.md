# MCP Tools

Public tools should call allowlisted workflows only. Do not expose raw connector execution or provider-specific trading/order commands.

## Public tools

### `worldcup_search_markets`

Backed by `worldcup-search-markets`.

Inputs:

- `query`: natural-language market search query, default `FIFA World Cup 2026`
- `team`: optional team filter
- `source`: `all`, `polymarket`, or `kalshi`
- `status`: `open`, `closed`, or `all`
- `limit`: result cap
- `force_live`: bypass cache preference and fetch provider data

Returns:

- normalized `WorldCupMarket[]`
- source counts
- warnings/caveats

### `worldcup_get_market_state`

Backed by `worldcup-get-market-state`.

Inputs:

- `market_id`: cache id from search/sync (`kalshi:<ticker>` | `polymarket:<id>`) — required
- `include_book`, `include_history`, `include_trades`: section toggles
- `history_hours`, `period_interval` (Kalshi candles), `history_interval`/`history_fidelity` (Polymarket)

Returns:

- refreshed `WorldCupMarket` + per-outcome order book (computed best bid/ask/spread)
- price history `[{ts, price, volume}]`, last trade / recent trades
- warnings (missing depth, stale, degraded sections)

### `worldcup_get_event_context`

Backed by `worldcup-get-event-context`.

### `worldcup_get_iptc_event_context`

Backed by `worldcup-get-iptc-event-context`.

### `worldcup_get_player_performance_context`

Backed by `worldcup-get-player-performance-context`.

Inputs:

- `event_urn` or `fixture_id`: fixture identifier; `event_urn` resolves same-pod event state
- `player_id`: optional API-Football player id filter
- `team_id`: optional API-Football team id filter
- `official_fifa_power_ranking`: optional official FIFA payload when already available

Returns:

- `official_fifa_power_ranking`: source-labeled official FIFA fields, default `pending`
- `machina_provisional_performance_signal`: provider-backed 0-10 provisional scores with confidence/drivers
- 20-minute eligibility status and warnings

### `worldcup_compare_market_sources`

Backed by `worldcup-compare-market-sources`.

### `worldcup_find_market_edges`

Backed by `worldcup-find-market-edges`.

Returns research candidates only; no execution advice.

### `worldcup_generate_market_brief`

Backed by `worldcup-generate-market-brief`.

### `worldcup_fan_sentiment_context`

Backed by `worldcup-fan-sentiment-context`.

## Internal/admin tools

### `worldcup_sync_market_sources`

Backed by `worldcup-sync-market-sources`.

Refreshes the same-pod `worldcup:market-cache` document collection from Sports Skills, Polymarket, and Kalshi search results.

### `worldcup_ingest_fixtures`

Backed by `worldcup-ingest-fixtures`.

### `worldcup_refresh_prematch_enrichment`

Backed by `worldcup-refresh-prematch-enrichment`.

## Connector utilities installed by this template

### `worldcup-market-intelligence.normalize_market_sources`

Read-only utility connector. Normalizes Sports Skills/Kalshi/Polymarket payloads into stable `WorldCupMarket` records.

### `worldcup-market-intelligence.filter_cached_markets`

Read-only utility connector. Applies query/team/source/status filters to cached `WorldCupMarket` records and warns when served prices are stale.
