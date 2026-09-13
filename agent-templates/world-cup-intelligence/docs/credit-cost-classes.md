# Credit Cost Classes

Canonical classes for Core/API gateway metering. These MUST stay in sync with
the public pricing on machina.gg/world-cup-api — the landing publishes the
numbers, so this table is the single source of truth for tool descriptions
and gateway config.

| Class          | Credits | Endpoints (examples)                                          |
|----------------|---------|---------------------------------------------------------------|
| `health`       | free    | health (whoami/smoke)                                         |
| `data`         | 1       | resolve, get-schedule, get-event-context, standings, squads, injuries, player-performance-context, calibration (Brier/reliability per source + weights; arithmetic only), competitions (registry read) |
| `market`       | 3       | search-markets, get-market-state, market-movers, compare-market-sources |
| `social`       | 8       | fan-pulse, fan-sentiment-context (xAI/Grok)                   |
| `intelligence` | 12      | generate-market-brief, explain-market-move; completed-catalog get-match-forecast/backtest-forecasts are precomputed archive reads |
| `edge`         | 18      | find-market-edges, get-signal                                 |
| `skill`        | 25–60   | match-preview, market-watch; completed-catalog match-recap/player-spotlight are immutable archive reads |

Notes:

- `intelligence` was previously called `reasoning` in this doc; the public
  name is `intelligence`.
- Every MCP tool description should quote its class + cost so budget-managing
  agents can predict spend before calling.
- Responses should carry `credits_used` (and ideally `credits_remaining`) in
  the envelope.
