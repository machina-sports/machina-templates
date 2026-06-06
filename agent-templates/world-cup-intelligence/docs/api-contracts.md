# World Cup Intelligence API Contracts

Public gateway routes should call only allowlisted workflows from this template. Do not expose raw workflow or connector execution.

All public routes are **read-only** market & match intelligence. Execution, betting placement, trading, and portfolio actions are out of scope.

## Identifiers

Every entity has a **canonical machina URN** minted deterministically from intrinsic attributes (stable across providers):

- event: `urn:machina:sport:soccer:event:{home-slug}-vs-{away-slug}:{YYYYMMDD}:wor`
- team: `urn:machina:sport:soccer:team:{name-slug}:{iso3}`
- player: `urn:machina:sport:soccer:player:{name-slug}:{YYYYMMDD-dob}:{iso3}`
- competition: `urn:machina:sport:soccer:competition:fifa-world-cup-2026:wor`
- venue: `urn:machina:sport:soccer:venue:{name-slug}:{iso3}` (omitted when the provider gives no venue)

`iso3` is the ISO-3166 alpha-3 country code (lowercased); the UK home nations use their FIFA codes (`eng`, `sco`, `wal`) since they have no ISO alpha-3. Players are minted only when a verified birth date exists (no placeholder date).

### Uniform `provider_ids`

Every doc (event, team, player, competition) carries a uniform `provider_ids` map: **one key per provider whose value is that provider's id for THIS object**.

- event: `{api_football: <fixture id>, sportradar: <sr:sport_event id>, opta: <match id>, entain: <fixture id>}`
- team: `{api_football, espn, opta, sportradar, entain}`
- player: `{api_football, espn, opta, sportradar}`
- competition: `{api_football, espn, sportradar, entain}`

No secondary ids (team/league/venue) live in `provider_ids` — those are resolved relationally (event `sport:competitors[].@id` → team crosswalk → that team's `provider_ids.api_football`; league via the competition). No internal `raw_provider` tag is exposed.

**Provider roles:** API-Football is the match-data source; sports-skills (ESPN) is fallback/enrichment; entain/sportradar/opta supply **ids only** (never their match data).

**Coverage note (provider-availability capped):** teams 100% on all 5 providers; events 100% on api_football/sportradar/opta/entain (ESPN event ids unavailable pre-tournament); players 100% api_football, ~92% espn, ~86% sportradar, ~27% opta (rises via the daily sync); no entain player ids exist.

**Alternate key:** reads accept the canonical `event_urn` OR `provider_event_id` (the API-Football fixture id, e.g. `1489417`, stored at `provider_ids.api_football`) — the latter is the stable, simple handle for clients. Markets are keyed by `{source}:{source_market_id}` (e.g. `polymarket:2415458`).

## Public (allowlisted) workflow set

**Identity & fixtures**
- `worldcup-resolve` — any provider id / URN → canonical entity + cross-provider ids
- `worldcup-get-schedule` — fixtures, filter by date/team/status
- `worldcup-get-event-context` — enriched match context (event + grounded prematch research + sports context)
- `worldcup-get-iptc-event-context` — IPTC/semantic event shape
- `worldcup-get-standings` — group tables
- `worldcup-get-squads` — both teams' squads
- `worldcup-get-injuries` — injuries/suspensions
- `worldcup-get-player-performance-context` — player performance signals

**Market intelligence**
- `worldcup-search-markets` — market search (Kalshi + Polymarket, URN-linked)
- `worldcup-get-market-state` — current price + order-book depth + price history + trades (live)
- `worldcup-market-movers` — biggest price moves over a lookback window
- `worldcup-compare-market-sources` — cross-venue price comparison
- `worldcup-find-market-edges` — informational edge/arb candidates (AI)
- `worldcup-explain-market-move` — why a price moved, grounded (AI)
- `worldcup-generate-market-brief` — grounded market-intelligence brief (AI)
- `worldcup-fan-sentiment-context` — social/news pulse (AI, grok)

**Agents (conversational)** — `world-cup-intelligence-agent` (full read+market), `world-cup-market-analyst-agent` (market-focused). Activate before exposing.

## Internal/admin workflow set (cron-driven, not exposed)

- `worldcup-ingest-fixtures` — fetch fixtures + mint events + inline event crosswalk (cron `0 5 * * *`)
- `worldcup-sync-market-sources` — refresh market cache + entity links + hourly snapshots (cron `*/30 * * * *`)
- `worldcup-sync-player-crosswalk` — rebuild player crosswalk (cron `0 6 * * *`)
- `worldcup-sync-team-crosswalk`, `worldcup-sync-event-crosswalk`, `worldcup-sync-identity-crosswalk` — identity sync
- `worldcup-refresh-prematch-enrichment` — grounded prematch research onto event docs
- `worldcup-health` — ops health check

## Freshness tiers

- **Identity / fixtures** — synced docs; teams/events stable, players refresh daily (06:00 UTC).
- **Market cache** (`search-markets`) — refreshed every 30 min; responses carry a staleness warning past 15 min.
- **`get-market-state`** — live from the source (current price, order book, history, trades).
- **`market-movers`** — computed from the hourly `worldcup:market-snapshot` time series; needs ≥2 hourly buckets to show movement.

## AI models

- Grounded search steps (`invoke_search`: prematch enrichment, brief context, move news) → **`gemini-3.1-flash-lite`** (fast; Google grounding carries factual quality).
- Reasoning/synthesis steps (`invoke_prompt`: brief synthesis, move explanation, edge analysis) → **`gemini-3.5-flash`**.
- Fan sentiment / live social (`grok` `post-responses`) → **`grok-4.3`**.

## Connector and secret requirements

- `api-football` connector + vault secret `TEMP_CONTEXT_VARIABLE_API_FOOTBALL_API_KEY` (fixtures, standings, squads, injuries, player stats).
- `sports-skills` connector (Kalshi/Polymarket/ESPN orchestration).
- `sportradar-soccer` + `TEMP_CONTEXT_VARIABLE_SPORTRADAR_SOCCER_V4_API_KEY`, `opta` (stats-perform) + `MACHINA_CONTEXT_VARIABLE_OPTA_OUTLET`/`_SECRET`, `bwin` + `TEMP_CONTEXT_VARIABLE_BWIN_ACCESS_ID`/`_TOKEN` — provider-id crosswalks only.
- `google-genai` + `TEMP_CONTEXT_VARIABLE_VERTEX_AI_CREDENTIAL` + `_VERTEX_AI_PROJECT_ID` (Gemini).
- `grok` + `MACHINA_CONTEXT_VARIABLE_GROK_API_KEY` (fan sentiment).

Secret lookup uses the literal name after `$` in a workflow's context-variables.

---

## `worldcup-resolve`

Resolve any provider id (api_football, sportradar, opta, entain, espn, transfermarkt) **or** a canonical machina URN to the entity it identifies (team / player / event / competition), with all cross-provider ids attached.

Request:

```json
{ "id": "sr:competitor:4748" }
```

Response:

```json
{
  "entity": {
    "_id": "urn:machina:sport:soccer:team:brazil:bra",
    "@type": ["sport:IdentityCrosswalk", "sport:Team"],
    "name": "Brazil",
    "country": "Brazil",
    "provider_ids": {"api_football": "6", "espn": "205", "opta": "ajab3...", "sportradar": "sr:competitor:4748", "entain": "234214"}
  },
  "entities": ["...all matches..."],
  "count": 1
}
```

Accepts: a machina URN (`urn:machina:…`), a fixture id (`1489389` → the event), any team/player provider id. Returns `entities: []` / `count: 0` when nothing matches. Searches both the identity-crosswalk (teams/players/competition) and the event store.

## Normalized WorldCupMarket shape

`worldcup-sync-market-sources` and `worldcup-search-markets` normalize Kalshi/Polymarket/Sports Skills records into this shape, then `link_market_entities` adds `competition_urn` / `related_team_urns` / `event_urn`.

```json
{
  "metadata": {"cache_id": "kalshi:KXWCGAME-26JUN19BRAHTI-BRA"},
  "id": "kalshi:KXWCGAME-26JUN19BRAHTI-BRA",
  "cache_id": "kalshi:KXWCGAME-26JUN19BRAHTI-BRA",
  "source": "kalshi",
  "source_market_id": "KXWCGAME-26JUN19BRAHTI-BRA",
  "source_event_id": "KXWCGAME-26JUN19BRAHTI",
  "title": "Brazil vs Haiti Winner?",
  "status": "open",
  "outcomes": [{"name": "Brazil", "price": 0.9, "source_outcome_id": "yes", "token_id": null}],
  "volume": 10818.56,
  "liquidity": null,
  "spread": null,
  "competition_urn": "urn:machina:sport:soccer:competition:fifa-world-cup-2026:wor",
  "related_team_urns": ["urn:machina:sport:soccer:team:brazil:bra", "urn:machina:sport:soccer:team:haiti:hti"],
  "event_urn": "urn:machina:sport:soccer:event:brazil-vs-haiti:20260620:wor",
  "fetched_at": "2026-06-06T15:17:27Z",
  "resolution_risk_notes": ["Read-only market intelligence. Verify provider resolution rules, fees, liquidity, and freshness before acting."]
}
```

**Market entity linking is implemented**: every cached market carries `competition_urn` (always the canonical WC competition), `related_team_urns` (team-name match against the crosswalk, with nation aliases), and `event_urn` for two-team markets matched to a fixture by team pair. Outright markets (winner/top-scorer/group) have ≤1 team and no `event_urn`.

## `worldcup-search-markets`

Search same-pod cached markets first, then optionally fall back to live provider search.

Request: `{ "query": "Brazil", "source": "all", "status": "open", "limit": 20, "force_live": false }`

Response: `{ "markets": [WorldCupMarket], "count": 8, "sources": {...}, "warnings": [] }`

- `source` ∈ `all|polymarket|kalshi`. `force_live=true` bypasses cache preference.
- Records are filtered for World Cup/FIFA relevance.

## `worldcup-get-market-state`

Resolve a `market_id` to current state, order-book depth, price history, and trades (live).

Request: `{ "market_id": "kalshi:KXWCGAME-26JUN19BRAHTI-BRA", "include_book": true, "include_history": true, "history_hours": 24 }`

Response: `{ market_id, source, market, book {outcomes[{name,bids[],asks[],best_bid,best_ask,spread}]}, history [{ts,price,volume}], trades [], warnings [] }`

- `market_id` namespace = `kalshi:<ticker>` | `polymarket:<id>`.
- Kalshi asks implied from the opposite side's bids; depth needs `sports-skills >= 0.25.3`.
- Best bid/ask computed by sorting levels (provider ordering not trusted).

## `worldcup-market-movers`

Biggest price moves across cached markets over a lookback window, from the `worldcup:market-snapshot` hourly time series.

Request: `{ "window_hours": 24, "limit": 20 }`

Response: `{ "movers": [{cache_id, title, source, outcome, price_now, price_then, delta, abs_delta, since, volume, event_urn, related_team_urns}], "count": 20 }`

Ranked by absolute price move vs the earliest snapshot in the window. Needs ≥2 hourly snapshots to surface movement.

## `worldcup-find-market-edges`

Request: `{ "min_edge_bps": 100, "include_reasoning": true, "limit": 50 }`

Returns `edge_candidates[]` — `within_venue_book_sum` (Kalshi YES prices summing off 1.0) or `cross_venue_draw` (Kalshi tie vs Polymarket draw) — plus `analysis` (gemini-3.5-flash, with fee/liquidity/resolution caveats). Informational only.

## `worldcup-explain-market-move`

Request: `{ "market_id": "kalshi:…", "window_hours": 24, "min_move_bps": 200 }`

Returns `move` (`moved`, `net_move_bps`, `swing_bps`, `direction`, from/to price+ts) and, when moved, `explanation` (grounded, cited drivers classified confirmed/speculative/noise).

## `worldcup-generate-market-brief`

Request: `{ "event_urn": "urn:…event:brazil-vs-haiti:20260620:wor", "depth": "standard", "include_social_pulse": false }`

Returns `brief` (headline, summary, key_factors, market_snapshot, risks_and_uncertainties, watch_items) — grounded search (lite) + synthesis (flash).

## `worldcup-fan-sentiment-context`

Request: `{ "query": "Brazil World Cup", "lookback_hours": 48, "force_live": true }`

Returns `fan_sentiment` (home/away narratives, breaking_news, buzz_level, narrative_threads, overall_sentiment) + `citations[]`, via grok-4.3 live X/web search.

## `worldcup-get-player-performance-context`

Player-level context from API-Football fixture player stats + optional official FIFA Power Ranking. Official FIFA fields and Machina provisional signals are kept separate. Scale 0–10; eligibility requires `minutes_played >= 20`; the official ranking is usually pending ~4h post-match.

## Guardrails

- Never expose raw connector execution publicly.
- Never include betting/trading/order placement endpoints in the public allowlist.
- Do not use “guaranteed edge,” “guaranteed profit,” or “bet this” language.
- Return source, freshness, and resolution/liquidity caveats with market-intelligence outputs.
