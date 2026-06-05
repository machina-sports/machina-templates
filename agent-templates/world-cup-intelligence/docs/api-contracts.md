# World Cup Intelligence API Contracts

MCP/public gateway routes should call only allowlisted workflows from this template. Do not expose raw workflow or connector execution.

All public routes are read-only market intelligence. Execution, betting placement, trading, and portfolio actions are out of scope.

## Identifiers

Events, teams, and competitions use **canonical machina URNs** minted deterministically from intrinsic attributes (so they are stable across providers):

- event: `urn:machina:sport:soccer:event:{home-slug}-vs-{away-slug}:{YYYYMMDD}:wor`
- team: `urn:machina:sport:soccer:team:{name-slug}:{iso3}`
- competition: `urn:machina:sport:soccer:competition:{name-slug}:wor`
- venue: `urn:machina:sport:soccer:venue:{name-slug}:{iso3}` (omitted when the provider gives no venue)

Every event doc also carries `provider_ids` (`api_football_fixture_id|home_team_id|away_team_id|league_id|venue_id`, plus entain/sportradar/opta/espn ids when mapped). **API-Football is the data source; sports-skills (ESPN/Transfermarkt) is fallback/enrichment; entain/sportradar/opta supply ids only (never their match data).**

**Alternate key:** reads accept the canonical `event_urn` OR `provider_event_id` (the API-Football fixture id, e.g. `1489417`) — the latter is the stable, simple handle for clients. Markets are keyed by `{source}:{source_market_id}` (e.g. `polymarket:2415458`).

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
- `worldcup-get-player-performance-context`
- `worldcup-compare-market-sources`
- `worldcup-find-market-edges`
- `worldcup-explain-market-move`
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

## `worldcup-get-player-performance-context`

Builds a player-level context package from API-Football fixture player stats and optional official FIFA Power Ranking data. Official FIFA/Aramco fields and Machina provisional signals are intentionally separate.

Request:

```json
{
  "event_urn": "urn:machina:sport:soccer:event:brazil-vs-serbia:20260615:wor",
  "fixture_id": "123",
  "player_id": "10",
  "team_id": "7",
  "official_fifa_power_ranking": {}
}
```

Response:

```json
{
  "player_performance_context": {
    "event": {"_id": "urn:machina:sport:soccer:event:brazil-vs-serbia:20260615:wor"},
    "player": {
      "player_id": "10",
      "name": "Alex Creator",
      "team_id": "7",
      "team_name": "Brazil",
      "position": "M",
      "is_goalkeeper": false,
      "minutes_played": 87,
      "eligible_for_power_ranking": true
    },
    "official_fifa_power_ranking": {
      "status": "pending",
      "expected_available_at": null,
      "source": "fifa.com",
      "scores": {
        "attacking": null,
        "creativity": null,
        "defending": null,
        "in_possession": null,
        "defending_goal": null
      },
      "classification": {
        "match_rank": null,
        "tournament_rank": null,
        "category_rankings": []
      }
    },
    "machina_provisional_performance_signal": {
      "status": "available",
      "source_quality": "provider",
      "confidence": 0.9,
      "scores_0_10": {
        "attacking": 7.0,
        "creativity": 8.1,
        "defending": 6.4,
        "in_possession": null,
        "defending_goal": null
      },
      "drivers": [],
      "warnings": [],
      "disclaimer": "Machina provisional signal only; not an official FIFA Power Ranking."
    },
    "context_and_evidence": {
      "fallback_path": ["api-football"],
      "citations": [],
      "missing_info_flags": [],
      "freshness": {"official_fifa_expected_lag_hours": 4}
    }
  }
}
```

Notes:

- Scale is 0-10.
- FIFA public category taxonomy: outfield = attacking, creativity, defending; goalkeepers = in possession, defending goal.
- Eligibility requires `minutes_played >= 20`.
- The official ranking is usually pending for ~4 hours post-match; provisional scores are a faster context layer, not official FIFA data.

## `worldcup-find-market-edges`

Scans the cached markets and cross-venue match pairs for dislocations.

Request: `{ "min_edge_bps": 100, "include_reasoning": true, "limit": 50 }`

Returns `edge_candidates[]`, each either:
- `within_venue_book_sum` — a Kalshi event whose outcome YES prices sum away from 1.0 (`book_sum`, `edge_bps`, `direction`, `legs[]`)
- `cross_venue_draw` — Kalshi tie price vs Polymarket draw price for a matched game (`delta`, `edge_bps`, `cheaper_venue`)

Plus `analysis` (gemini-3.5-flash explanation with fee/liquidity/resolution caveats). Informational only; never trade execution.

## `worldcup-explain-market-move`

Detects the largest price move for a `market_id` over a window and explains it.

Request: `{ "market_id": "kalshi:KXWCGAME-...-FRA", "window_hours": 24, "min_move_bps": 200 }`

Returns `move` (`moved`, `net_move_bps`, `swing_bps`, `direction`, from/to price + ts) and, when moved, `explanation` (grounded, cited drivers classified confirmed/speculative/noise). Uses `get_price_history` (normalized 0-1) + `invoke_search`.

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
