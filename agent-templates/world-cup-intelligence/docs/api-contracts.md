# World Cup Intelligence API Contracts

MCP/public gateway routes should call only allowlisted workflows from this template. Do not expose raw workflow or connector execution.

All public routes are read-only market intelligence. Execution, betting placement, trading, and portfolio actions are out of scope.

## Identifiers

Events are keyed by provider URNs built deterministically from API-Football ids: `urn:apifootball:sport_event:{id}` (teams, leagues, and venues follow the same `urn:apifootball:{type}:{id}` pattern). Markets are keyed by `{source}:{source_market_id}` (e.g. `polymarket:2415458`).

Market-to-event entity linking (matching a Kalshi/Polymarket market to a specific fixture) is **planned, not implemented**. Markets are discovered by `query`/`team` text search, not by event id.

## Connector and secret requirements

- `worldcup-ingest-fixtures` needs the `api-football` connector and a vault secret named `API_FOOTBALL_API_KEY`.
- `worldcup-fan-sentiment-context` needs the `grok` connector (this repo) and a vault secret named `MACHINA_CONTEXT_VARIABLE_GROK_API_KEY`.
- `worldcup-generate-market-brief`, `worldcup-refresh-prematch-enrichment`, and `worldcup-find-market-edges` need the `google-genai` connector (this repo) and vault secrets `TEMP_CONTEXT_VARIABLE_VERTEX_AI_CREDENTIAL` + `TEMP_CONTEXT_VARIABLE_VERTEX_AI_PROJECT_ID`. Grounded prematch research uses `invoke_search` (Google Search grounding); all reasoning runs on `gemini-3.5-flash`.

Secret lookup uses the literal name after `$` in a workflow's context-variables.

## Launch workflow set

- `worldcup-search-markets`
- `worldcup-get-market-state`
- `worldcup-get-event-context`
- `worldcup-get-iptc-event-context`
- `worldcup-compare-market-sources`
- `worldcup-find-market-edges`
- `worldcup-generate-market-brief`
- `worldcup-fan-sentiment-context`

## Internal/admin workflow set

- `worldcup-sync-market-sources`
- `worldcup-ingest-fixtures`
- `worldcup-refresh-prematch-enrichment`
- `worldcup-health`

## Normalized WorldCupMarket shape

`worldcup-sync-market-sources` and `worldcup-search-markets` normalize Kalshi/Polymarket/Sports Skills records into this cache/API shape before returning data or writing to `worldcup:market-cache`.

```json
{
  "metadata": {"cache_id": "polymarket:2415458"},
  "id": "polymarket:2415458",
  "cache_id": "polymarket:2415458",
  "source": "polymarket",
  "source_market_id": "2415458",
  "source_event_id": "554734",
  "title": "Will Belgium reach the Round of 16 at the 2026 FIFA World Cup?",
  "description": "Provider resolution text when available",
  "slug": "will-belgium-reach-the-round-of-16-at-the-2026-fifa-world-cup-...",
  "status": "open",
  "market_type": "group_stage_or_round_market",
  "outcomes": [
    {
      "name": "Yes",
      "price": 0.61,
      "token_id": "7804...",
      "source_outcome_id": "7804..."
    }
  ],
  "volume": 998.49,
  "liquidity": 1200.0,
  "spread": 0.03,
  "start_time": "2026-06-01T00:00:00Z",
  "end_time": "2026-06-15T00:00:00Z",
  "updated_at": "2026-06-03T22:04:11Z",
  "fetched_at": "2026-06-03T22:10:00Z",
  "resolution_risk_notes": [
    "Read-only market intelligence. Verify provider resolution rules, fees, liquidity, and freshness before acting."
  ],
  "source_payload_keys": ["id", "question", "outcomes"]
}
```

## `worldcup-search-markets`

Search same-pod cached markets first, then optionally fall back to live Sports Skills, Polymarket, and Kalshi search.

Request:

```json
{
  "query": "Brazil World Cup",
  "team": "Brazil",
  "source": "all",
  "status": "open",
  "limit": 20,
  "force_live": false
}
```

Response:

```json
{
  "markets": ["WorldCupMarket[]"],
  "count": 12,
  "sources": {
    "polymarket_records_seen": 50,
    "kalshi_records_seen": 0
  },
  "warnings": []
}
```

Notes:

- `source` accepts `all`, `polymarket`, or `kalshi`.
- `force_live=true` bypasses cache preference and returns fresh normalized provider data.
- Provider records are filtered for World Cup/FIFA/team/query relevance to avoid broad sports-market noise.

## `worldcup-get-market-state`

Resolve a `market_id` to current state, order-book depth, price history, and trades. Every read also refreshes the cached snapshot.

Request:

```json
{
  "market_id": "kalshi:KXWCGAME-26JUN16FRASEN-FRA",
  "include_book": true,
  "include_history": true,
  "include_trades": false,
  "history_hours": 24,
  "period_interval": 60
}
```

Response:

```json
{
  "market_id": "kalshi:KXWCGAME-26JUN16FRASEN-FRA",
  "source": "kalshi",
  "market": "WorldCupMarket (refreshed)",
  "book": {
    "outcomes": [
      {
        "name": "France",
        "token_id": null,
        "bids": [{"price": 0.69, "size": 568.15}],
        "asks": [{"price": 0.71, "size": 300.0}],
        "best_bid": 0.69,
        "best_ask": 0.71,
        "spread": 0.02
      }
    ]
  },
  "history": [{"ts": 1780545600, "price": 0.70, "volume": 140.72}],
  "last_trade": null,
  "trades": [],
  "warnings": []
}
```

Notes:

- `market_id` uses the cache id namespace from search/sync (`kalshi:<ticker>` | `polymarket:<id>`).
- Kalshi asks are implied from the opposite side's bids (ask_yes = 1 − bid_no); depth requires `sports-skills >= 0.25.3` and degrades with a warning below that.
- Polymarket depth/history/trades are per outcome token; history covers the primary outcome.
- Best bid/ask are computed by sorting levels — provider ordering is not trusted.

## `worldcup-sync-market-sources`

Internal/admin workflow that refreshes `worldcup:market-cache`.

Request:

```json
{
  "query": "FIFA World Cup 2026",
  "source": "all",
  "status": "open",
  "limit": 100
}
```

Response:

```json
{
  "markets_count": 100,
  "sources": {
    "polymarket_records_seen": 100,
    "kalshi_records_seen": 0
  },
  "warnings": []
}
```

Side effect:

- bulk-upserts normalized records to same-pod document store under `worldcup:market-cache`.

## Guardrails

- Never expose raw connector execution publicly.
- Never include betting/trading/order placement endpoints in the public allowlist.
- Do not use “guaranteed edge,” “guaranteed profit,” or “bet this” language.
- Return source, freshness, and resolution/liquidity caveats with market-intelligence outputs.
