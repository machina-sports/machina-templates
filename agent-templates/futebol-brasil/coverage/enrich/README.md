# Futebol Brasil — Coverage Enrich

Performant, brand-agnostic enrich pipeline for Brazilian football coverage. Pins
5 competitions and produces normalized documents that downstream content,
podcast, or widget templates can read without coupling to api-football's raw
shapes.

## Pinned competitions

Configured by `load-leagues-config.yml` into the `futebol-brasil-leagues-config`
document. Edit that document to enable/disable or rotate seasons — the pipeline
re-reads it on every run.

| Competition           | api-football ID         | Kind             |
| --------------------- | ----------------------- | ---------------- |
| Seleção Brasileira    | team `6` (no league_id) | national-team    |
| Brasileirão Série A   | league `71` (2026)      | league           |
| CONMEBOL Libertadores | league `13` (2026)      | continental-cup  |
| Copa do Brasil        | league `73` (2026)      | domestic-cup     |
| CONMEBOL Sudamericana | league `11` (2026)      | continental-cup  |

## Output documents

All documents are brand-agnostic (prefix `brasil-*`) and carry consistent
metadata so consumers can filter by `competition`, `league_id`, `season_id`,
and `updated_at`.

| Document name                                | Shape (key fields)                                                                                                                      | Cardinality                              |
| -------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------- |
| `brasil-fixture` (collection)                | `fixture_id, competition, league_id, season_id, date, status, venue, round, home_team{id,name,logo}, away_team{...}, goals, score`      | one doc per fixture                      |
| `brasil-standings-{competition}-{season}`    | `competition, league_id, season_id, league, groups:[{group_index, rows:[{rank, team_id, team_name, points, played, wins, draws, ...}]}]` | one doc per competition/season           |
| `brasil-competitor-{team_id}`                | `team_id, competition, team, players:[{id,name,age,number,position,photo}], players_count`                                              | one doc per team                         |
| `brasil-leaders-{competition}-{season}`      | `competition, league_id, season_id, leaders:[{rank, team_id, team_name, points, goalsDiff, ...}], leaders_kind: 'top-teams-by-points'`  | one doc per competition/season           |

> **Leaders semantics**: derived from `/standings` (top-N teams by points). The
> api-football connector exposed in this repo does not currently include
> `/players/topscorers`. When that operation is added to the connector, the
> `enrich-season-leaders` workflow can be extended to also save player-level
> leaders without changing the document name (just adds entries with a
> different `leaders_kind`).

## Sync markers (incremental gating)

Each load/enrich workflow writes a marker document into the
`futebol-brasil-sync-marker` collection, with a deterministic `title` of the
form `"Futebol Brasil | {Kind} {load|enrich} · {competition}[ · team {team_id}]"`
and a `synced_at` timestamp. The next run reads the marker by title first and
short-circuits with `workflow-status: skipped` if `force=False` and a marker
exists. The orchestrator flips `force=True` for an immediate refresh.

Suggested TTLs (override per run via `ttl_minutes` input):

| Pipeline        | Default TTL |
| --------------- | ----------- |
| fixtures        | 15 min      |
| standings       | 60 min      |
| season-leaders  | 120 min     |
| rosters         | 1440 min    |

## Workflows

### Config

- **`futebol-brasil-load-leagues-config`** — seeds (if missing) and reads the
  `futebol-brasil-leagues-config` document. Returns `leagues_config` and
  `enabled_leagues`.

### load-\* (raw fetchers, ad-hoc reusable)

| Workflow                                | Reads from api-football      | Writes                                       |
| --------------------------------------- | ---------------------------- | -------------------------------------------- |
| `futebol-brasil-load-fixtures`          | `get-fixtures`               | sync marker only                             |
| `futebol-brasil-load-standings`         | `get-standings`              | sync marker only                             |
| `futebol-brasil-load-rosters`           | `get-players/squad`          | sync marker only                             |
| `futebol-brasil-load-season-leaders`    | `get-standings`              | sync marker only                             |

### enrich-\* (fetch + normalize + bulk-save brand-agnostic docs)

| Workflow                                 | Output document(s)                                       |
| ---------------------------------------- | -------------------------------------------------------- |
| `futebol-brasil-enrich-fixtures`         | `brasil-fixture` (bulk-update, one per fixture)          |
| `futebol-brasil-enrich-standings`        | `brasil-standings-{competition}-{season}` (one doc)      |
| `futebol-brasil-enrich-rosters`          | `brasil-competitor-{team_id}` (one doc)                  |
| `futebol-brasil-enrich-season-leaders`   | `brasil-leaders-{competition}-{season}` (one doc)        |

### Coverage gateway + checkin/checkout

- **`futebol-brasil-coverage-gateway`** — reads config + last checkin/checkout +
  all sync markers in one call. Returns `enabled_leagues`, `last_checkin`,
  `last_checkout`, `sync_markers`, `in_progress`. Use this from dashboards,
  agents, or scheduled health checks.
- **`futebol-brasil-coverage-checkin`** — writes `futebol-brasil-coverage-checkin`
  with `run_id`, `trigger`, `started_at`.
- **`futebol-brasil-coverage-checkout`** — writes
  `futebol-brasil-coverage-checkout` with `run_id`, `status`, `summary`,
  `completed_at`. Sets `matches_checkin: True` when `run_id` matches the latest
  checkin (helps detect crashed runs).

### Agent

- **`futebol-brasil-coverage-enrich`** — orchestrates the full pipeline:
  `checkin` → `load-leagues-config` → per-league `enrich-fixtures` →
  `enrich-standings` → `enrich-season-leaders` → `enrich-rosters` (national
  team only) → `checkout`. Set `config-frequency: 60` minutes by default —
  adjust per project.

## Performance notes

- **Incremental by default.** Every workflow gates on a sync marker; recurring
  schedules at 5–10 min cost ~1 api-football call per pipeline only when stale.
- **Batched writes.** Fixtures use `bulk-update` keyed on a deterministic
  `fixture_id`, so re-runs are idempotent.
- **Per-league fan-out.** The agent uses `foreach` over `enabled_leagues`, so
  competitions run in sequence (predictable rate-limit footprint).
- **Cup safety.** `enrich-standings` and `enrich-season-leaders` no-op when
  `league_id is None` (Seleção Brasileira) or when the API returns no standings
  rows (pure knock-out cups in early stages).

## Credentials

Requires `TEMP_CONTEXT_VARIABLE_API_FOOTBALL_API_KEY` in the project vault
(same key consumed by the `connectors/api-football` connector).
