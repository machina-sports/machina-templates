# MCP Tools

Public tools should call allowlisted workflows only. Do not expose raw connector execution or provider-specific trading/order commands.

## Resolving a fixture to an `event_urn`

`worldcup_get_signal`, `worldcup_get_event_context`, and the scoped skill cards
key off a fixture `event_urn`. Callers rarely have one in hand, so every
fixture-scoped tool now accepts human identifiers and resolves internally:

- Pass `event` free text ("Brazil vs Morocco" — also `v` / `x` / `-`
  separators), or `team` (+ optionally `opponent` + `date` as `YYYY-MM-DD`).
  This matches the public landing's own example payload
  `{ "event": "Brazil vs Morocco" }`.
- `worldcup_player_spotlight` likewise accepts `player` (name) + optional
  `team` and resolves the `player_urn` via the identity crosswalk
  (slug-based, accent/case-insensitive; ambiguity returned as `candidates`).
- The tool echoes the resolved `event_urn`/`player_urn` (and
  `resolved_fixture`/`resolved_player`) so it can be reused across calls, and
  embeds it in the `skill_card` body.
- If nothing resolves, the tool returns an explicit `recommendation` /
  `warnings` message ("No fixture resolved …") rather than an empty payload.

Resolution is deterministic (substring/slug matching over same-pod cached
docs) — no LLM call, no extra credits, no hallucinated-URN risk.

To discover URNs directly, expose **`worldcup_get_schedule`** (filter by
`team`/`opponent`/`date_from`/`date_to`; returns fixtures with `event_urn`) and
**`worldcup_resolve`** (any provider id or canonical URN → entity). Keep at
least one of these on every deployed MCP surface — without a discovery primitive
`worldcup_get_signal` is unreachable.

## Recommended MCP surface (tiers)

| Tier | Tools | Credit class |
|------|-------|--------------|
| Discover | `resolve`, `get_schedule`, `health` | data (1) / free |
| Skills | `match_preview`, `match_recap`, `player_spotlight`, `fan_pulse`, `market_watch` | skill (25–60) |
| Context & markets | `get_event_context`, `search_markets`, `get_market_state` | data (1) / market (3) |
| Forecast & intelligence | `get_match_forecast`, `get_signal`, `find_market_edges`, `explain_market_move`, `backtest_forecasts` | intelligence (12) / edge (18) |

Internal-only (never expose): `sync-*`, `ingest-*`, `seed-*`, `refresh-*`,
`log-signals`, `coverage-gateway`.

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

### `worldcup_stable_markets`

Backed by `worldcup-stable-markets`.

Read-only worklist of markets whose cross-source quote has **stabilized** — the
explainable inverse of the unreliable-quote flag. Useful as a faster "safe to
re-enable" candidate signal than waiting on a traditional pricing feed.

Inputs:

- `window_hours`: snapshot lookback for the stable-streak history (default `24`)
- `spread_bps`, `movement_bps`, `agreement_bps`, `min_volume`: stability thresholds (defaults `200` / `150` / `150` / `1000`)
- `team`, `query`: optional filters
- `limit`: result cap (default `50`)

Returns:

- `stable_markets`: worklist sorted most-recently-stabilized first, each with `stable_since`, `confidence` (`provisional` | `stable` | `corroborated`), and an explainable `drivers` list
- `thresholds`: the thresholds applied
- `warnings`: caveats, incl. that detection-vs-feed latency is not benchmarked

Read-only; no pricing or execution advice.

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

## Pod schedule topology (ops)

| Agent | Mechanism | Cadence | Runs |
|---|---|---|---|
| `worldcup-market-sync` | **template, `config-frequency: 15`** | 15 min | gateway, then market sync when no match is live |
| `worldcup-coverage-hot` | pod `jobs` cron | `*/2 * * * *` | gateway always; market sync + live status **only when `has_live`** |
| `worldcup-content-author` | pod `jobs` cron | `*/15 * * * *` | market-watch + fan-pulse when live/upcoming/recent |
| `worldcup-coverage-prematch-warm` | pod `jobs` cron | `0 */6 * * *` | prematch enrichment |
| `worldcup-forecasts-daily` | pod `jobs` cron | `0 7 * * *` | model forecasts + signal ledger + backtest |
| `worldcup-ingest-fixtures-cron` | pod `jobs` cron | `0 5 * * *` | fixture ingest |
| `worldcup-sync-market-sources-cron` | pod `jobs` cron | — | **RETIRED** (see below) |

**Prefer the sportingbot idiom for recurring agents**: template YAML with
`context.config-frequency` (minutes) + `status: "active"`, installed via
import — the platform's native agent scheduler. The hand-registered
`jobs[].cron` mechanism proved unreliable on this pod: the 30-min sync cron
agent marked every fire "dispatched" but **never executed its workflow once**
(at :00/:30 it also always collided with the 2-min hot tick), and `update_agent`
changes to a jobs-based agent's workflow list were served stale by the
dispatcher. `worldcup-market-sync` replaced it and verified live.

**Agent-context leak**: an agent's own `context` (e.g. its lifecycle
`status: "active"`) is visible to its workflow-input expressions — an input
like `"$.get('status', 'open')"` resolves to `"active"` and silently breaks
downstream filters. Use literals (`"'open'"`) in agent workflow inputs.
