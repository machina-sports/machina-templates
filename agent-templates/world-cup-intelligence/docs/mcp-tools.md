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

### `worldcup_get_event_context`

Backed by `worldcup-get-event-context`.

### `worldcup_get_iptc_event_context`

Backed by `worldcup-get-iptc-event-context`.

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
