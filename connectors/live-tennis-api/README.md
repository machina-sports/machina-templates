# Live Tennis API Connector

Read-only connector for the [Live Tennis API](https://livetennisapi.com) — live
in-match state, scores, fixtures, players, tournaments, rankings and
head-to-head for ATP, WTA, Challenger, ITF and juniors.

**Disclosure:** this connector is contributed and maintained by the Live
Tennis API team, the vendor of the API it wraps. It packages a commercial API
with a free tier; it is not an independent or public-data source.

Origin: proposed as a keyed skill in
[machina-sports/sports-skills#125](https://github.com/machina-sports/sports-skills/issues/125);
the maintainers asked for it as a standalone connector here so that
`sports-skills` keeps its zero-key public-data boundary.

## What it does — and does not do

- **Read-only.** Every command is an HTTP `GET`. The connector never registers
  webhooks, never mints push tokens, never places or prices a bet and never
  moves money. The generic `invoke_request` command refuses any path outside
  a fixed allow-list of documented read routes.
- **No retries.** A `429` (or any non-2xx) is returned as
  `{"status": false, "message": ..., "data": {...}}` with the provider's
  stable error code and the `Retry-After` / `resets_at` hint. A retry loop
  would burn the free daily budget, so the decision is left to the workflow.
- **Provider payloads are returned unmodified** under a named key
  (`matches`, `match`, `score`, `fixtures`, `players`, `player`,
  `tournaments`, `rankings`, `h2h`, `usage`, `response`); list responses also
  carry the provider's `meta` (`limit`, `offset`, `count`, `total`,
  `has_more`). The one addition is a `derived` block (break-point state)
  beside each live match — see below.

## Prerequisites

1. **Get a key.** Sign up at <https://livetennisapi.com> — the FREE tier needs
   no card and gives live and upcoming matches, scores, players, tournaments
   and fixtures at **30 requests/minute, 100 requests/day**. Paid tiers
   (BASIC / PRO / ULTRA) unlock history, rankings listings, head-to-head,
   market prices and model fields at higher limits; see
   <https://docs.livetennisapi.com> for the current table.
2. **Store the key in the Machina vault** as
   `TEMP_CONTEXT_VARIABLE_LIVE_TENNIS_API_KEY` (one secret, one call):

   ```python
   create_secrets(
     name="TEMP_CONTEXT_VARIABLE_LIVE_TENNIS_API_KEY",
     key="[your key]"
   )
   check_secrets(name="TEMP_CONTEXT_VARIABLE_LIVE_TENNIS_API_KEY")
   ```

   The key is never written into this repository, into a workflow file or
   into the connector's environment. Workflows reference it through
   `context-variables` and pass it to each task as an input; the connector
   sends it as the `X-API-Key` header.
3. **Install the connector:**

   ```python
   get_local_template(
     template="connectors/live-tennis-api",
     project_path="/app/machina-templates/connectors/live-tennis-api"
   )
   ```

4. **Verify:** `execute_workflow(name="live-tennis-api-test-credentials")`
   calls `GET /usage` (FREE on every tier, one request) and returns the key's
   tier and quota. `workflow-status` is `executed` on a good key, `failed`
   otherwise.

## Components

### Connector (`live-tennis-api.yml`, `live-tennis-api.py`)

Base URL: `https://api.livetennisapi.com/api/public/v1` (from the published
OpenAPI spec, <https://docs.livetennisapi.com/openapi.yaml>). Every command
takes `api_key` plus the parameters below.

| Command | Endpoint | Tier | Parameters | Returns (`data.*`) |
|---|---|---|---|---|
| `get_usage` | `GET /usage` | FREE | — | `usage` — `{principal, tier, limits, today, ...}` |
| `get_live_matches` | `GET /matches?status=live` | FREE | `tour`, `draw`, `limit`, `offset` | `matches` (+ `derived` per match), `meta` |
| `get_matches` | `GET /matches` | FREE (`live`, `upcoming`); BASIC (`completed`, `cancelled`) | `status`, `tour`, `draw`, `player`, `country`, `tournament_id`, `from`, `to`, `updated_since`, `cursor`, `limit`, `offset` | `matches`, `meta` |
| `get_match` | `GET /matches/{matchId}` | FREE | `match_id` | `match`, `derived` |
| `get_match_score` | `GET /matches/{matchId}/score` | FREE | `match_id` | `score`, `derived` |
| `get_fixtures` | `GET /fixtures` | FREE | `tour`, `draw`, `limit`, `offset` | `fixtures`, `meta` |
| `search_players` | `GET /players` | FREE | `search`, `limit`, `offset` | `players`, `meta` |
| `get_player` | `GET /players/{playerId}` | FREE | `player_id` | `player` |
| `get_tournaments` | `GET /tournaments` | FREE | `search`, `tour`, `draw`, `limit`, `offset` | `tournaments`, `meta` |
| `get_rankings` | `GET /rankings` | PRO (listing) / ULTRA (per-player) | `system`, `tour`, `player`, `as_of`, `surface`, `min_matches`, `activity_weeks`, `limit`, `offset` | `rankings`, `meta` |
| `get_head_to_head` | `GET /h2h` | BASIC | `p1`, `p2` (name fragments, min 3 chars) | `h2h` — `{players, totals, by_surface, meetings, stats}` |
| `derive_match_state` | none (offline) | — | `score` | `state` — `{break_point, server, receiver, is_tiebreak, points_server, points_receiver}` |
| `invoke_request` | any allow-listed `GET` | per route | `path`, `path_id`, `query` | `response` |

Enumerations: `tour` is `atp | wta | challenger | itf | juniors`; `draw` is
`singles | doubles`; `status` is `live | upcoming | completed | cancelled`.
`limit` defaults to 50, maximum 200; page with `offset` until
`meta.has_more` is false. A tier the key does not hold answers `403` with
`error: upgrade_required`; the connector reports it and does not retry.

### Reading a score

Every score array is **player-major**: the first entry is player 1, the
second player 2.

```json
{
  "sets": [1, 0],
  "games": [[6, 3], [4, 4]],
  "points": ["30", "40"],
  "server": 1,
  "is_tiebreak": false,
  "timestamp": "2026-09-12T14:02:11Z"
}
```

reads: player 1 leads one set to nil, won the first set 6-4, the second set
is 3-4, player 1 is serving at 30-40. During a tiebreak `points` are the
running tiebreak count as integer strings (`"5"`, `"6"`) and `is_tiebreak`
is true. Entries can be `null` on completed matches.

### Derived break-point flag

`get_live_matches`, `get_match` and `get_match_score` attach a `derived`
block; `derive_match_state` computes the same thing offline from any
`score` object:

```json
{
  "break_point": true,
  "server": 1,
  "receiver": 2,
  "is_tiebreak": false,
  "points_server": "30",
  "points_receiver": "40"
}
```

`break_point` is `true` when the receiver is at `AD`, or at `40` while the
server is at `0`, `15` or `30`. It is `false` at deuce, at AD-server, and
always inside a tiebreak (there is no service game to break). It is `null`
whenever the state is unknown — no score, no server, a null or non-standard
point string — never guessed.

### Workflows

| Workflow | What it does |
|---|---|
| `live-tennis-api-test-credentials` | One `GET /usage`; returns tier and quota; `executed` / `failed`. |
| `live-tennis-api-sync-live-matches` | One `GET /matches?status=live` (inputs `tour`, `draw`, `limit`); flattens each match into a `live-tennis-api-match` document with the score fields and `break_point`; outputs `matches`, `matches_count`, `break_points` (match ids currently at break point), `error`. |
| `live-tennis-api-sync-fixtures` | One `GET /fixtures` (inputs `tour`, `draw`, `limit`); saves one `live-tennis-api-fixture` document per fixture. |

Example:

```python
execute_workflow(
  name="live-tennis-api-sync-live-matches",
  context={"tour": "atp", "draw": "singles", "limit": 50}
)
```

### Using the connector directly in your own workflow

```yaml
workflow:
  name: my-tennis-workflow
  context-variables:
    live-tennis-api:
      api_key: $TEMP_CONTEXT_VARIABLE_LIVE_TENNIS_API_KEY
  tasks:
    - type: connector
      name: load-live-matches
      connector:
        name: live-tennis-api
        command: get_live_matches
      inputs:
        api_key: "$.get('api_key')"
        tour: "'wta'"
      outputs:
        live: "$.get('matches', [])"
        at_break_point: "[m.get('id') for m in $.get('matches', []) if (m.get('derived') or {}).get('break_point')]"
```

## Error envelope

```json
{
  "status": false,
  "message": "Daily quota exhausted; resets at 2026-09-13T00:00:00Z. Do not retry before then.",
  "data": {
    "status_code": 429,
    "error": "rate_limited",
    "detail": "...",
    "path": "/matches",
    "scope": "day",
    "limit_per_day": 100,
    "resets_at": "2026-09-13T00:00:00Z",
    "retry_after": "3600"
  }
}
```

`error` is the provider's stable code (`rate_limited`, `abuse_throttled`,
`upgrade_required`, `not_found`, `bad_date`, ...). `401` means the key is
missing, unknown or disabled; `403` means the key's tier does not unlock the
route; `410` means the match id was merged into another record.

## Budgeting the free tier

Each command is exactly one request. Poll `get_live_matches` no more often
than the data changes for your use — a scheduled agent running it every two
minutes spends 30 of the 100 daily requests per hour of play. Use
`get_match_score` for a single match you are following; use `get_usage` to
read the remaining budget rather than probing.

## Tests

Offline only — no network, no key:

```bash
python -m pytest connectors/live-tennis-api/tests -q
```

## Reference

- Documentation: <https://docs.livetennisapi.com>
- OpenAPI: <https://docs.livetennisapi.com/openapi.yaml>
- Plans and limits: <https://livetennisapi.com>

v0.1.0
