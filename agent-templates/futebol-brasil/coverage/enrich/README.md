# Futebol Brasil — Coverage / Enrich

Performant, incremental coverage module for the 5 pinned Brazilian
football targets. Reuses the existing `api-football` connector — does
NOT install a duplicate source.

## Scope (5 targets, data-driven)

| key                  | id            | source                | written docs                                   |
| -------------------- | ------------- | --------------------- | ---------------------------------------------- |
| `brasileirao-serie-a`| league 71     | api-football          | competition, fixture, standings, leaders, roster, competitor |
| `libertadores`       | league 13     | api-football          | competition, fixture, standings, leaders, competitor          |
| `copa-do-brasil`     | league 73     | api-football          | competition, fixture, leaders, competitor                     |
| `sudamericana`       | league 11     | api-football          | competition, fixture, standings, leaders, competitor          |
| `selecao`            | team 6        | api-football          | fixture, roster, competitor                                   |

Competition ids are seeded by `load-leagues-config.yml` and stored in the
`futebol-brasil-coverage-config` document so they can be reconfigured
without redeploying the template.

## Documents written (brand-agnostic, `brasil-*` namespace)

| document name              | shape                                                                                            | key metadata                          |
| -------------------------- | ------------------------------------------------------------------------------------------------ | ------------------------------------- |
| `futebol-brasil-coverage-config` | seed config: pinned competitions + national teams + per-resource stale_hours              | `scope`                               |
| `futebol-brasil-competition` | per-league control plane: `version_control` (`*_synced_at`), `staleness_policy`, `has_*` flags | `league_id`, `season`, `key`          |
| `brasil-fixture`           | slim fixture: status, teams, goals, score, venue, league                                         | `fixture_id`, `league_id`, `season`, `home_team_id`, `away_team_id`, `status_short`, `date`, `competition`, `updated_at` |
| `brasil-standings`         | league table: rows[] with rank, points, goalsDiff, form, all/home/away                           | `league_id`, `season`, `competition`, `updated_at` |
| `brasil-leaders`           | team-leader categories computed from standings: top_points, top_attack, top_defense, top_goal_diff, top_form | `league_id`, `season` |
| `brasil-roster`            | squad of ONE team: players[], players_count, synced_at                                            | `team_id`, `league_id`, `season`      |
| `brasil-competitor`        | per-team rollup: standings row + roster summary + last 5 + next 5 fixtures                       | `team_id`, `league_id`, `season`      |

The two `futebol-brasil-*` documents (`coverage-config`, `competition`)
are the **control plane** — they're not consumed by frontends. Everything
a UI or downstream agent needs reads from the `brasil-*` namespace.

## Architecture (per tick)

```
                ┌─── futebol-brasil-coverage-checkin
                │      (pick least-recently checked-out league, lock)
                ▼
        futebol-brasil-coverage-gateway
                │      (zero-API; reads version_control + staleness_policy)
                ▼
   ┌────────────┼────────────┬────────────┐
   ▼            ▼            ▼            ▼
load-fixtures  load-      load-season-  load-rosters (foreach team)
               standings  leaders
               (derived from standings; cheap re-projection)
   │            │            │            │
   └────────────┴─────┬──────┴────────────┘
                     ▼
            enrich-competitor (foreach team — joins standings + roster + fixtures)
                     │
                     ▼
        futebol-brasil-coverage-checkout
                (release lock + stamp last_full_refresh_at)
```

The agent runs ONE competition per tick, auto-rotating via the
check-in's "least-recently checked-out" sort. Combined with
`config-frequency: 1` (minute), that gives the 4 league agents a
~4-minute end-to-end refresh ceiling — well below the
`fixtures_stale_hours: 1` budget.

The national team (Seleção) runs on a separate agent
(`futebol-brasil-coverage-selecao`) at 6h cadence — rosters are slow-moving
and fixtures are sparse outside FIFA windows.

## Performance discipline

- **Incremental**: every load-* checks the competition doc's
  `version_control.<resource>_synced_at` and skips when fresher than
  the per-resource `staleness_policy.<resource>_stale_hours`.
- **Batch**: every persistence is `bulk-update` with a deterministic
  `title` key; one round-trip per resource per league.
- **Idempotent**: re-running any workflow is a no-op when nothing
  drifted. Force-refresh via `force: True` input.
- **Soft-locked**: `processing` flag on the competition doc prevents
  two concurrent ticks racing the same league. The checkout always
  runs (no condition) so stuck locks self-heal.
- **Zero LLM, zero mock**: every document is a deterministic
  projection of an api-football response.

## First-run bootstrap

```bash
# Seed the config doc (5 pinned competitions)
machina workflow run futebol-brasil-coverage-load-leagues-config

# Seed the 4 competition control docs
machina workflow run futebol-brasil-coverage-load-competitions

# Run one tick of the league agent (auto-picks the first competition)
machina agent run futebol-brasil-coverage-enrich --sync

# Run one tick of the Seleção agent
machina agent run futebol-brasil-coverage-selecao --sync

# Enable the agents to run on schedule (Studio: set status to active)
```

## Notes / known limitations

- **Player-level season leaders** (top-scorers, top-assists) require
  the `/players/topscorers` and `/players/topassists` endpoints. They
  are NOT exposed by the api-football connector in this project, so
  `brasil-leaders` falls back to **team-level** leaders aggregated
  from the standings (top_points / top_attack / top_defense /
  top_goal_diff / top_form). When the connector gains player-level
  top* commands, swap the `aggregate-leaders` task in
  `load-season-leaders.yml` for a connector fetch — the document
  shape and consumers stay the same.
- **Copa do Brasil** is `has_standings: False` (single-elimination
  cup); the gateway always emits `should-load-standings: False` for it.
  Leaders for Copa do Brasil are therefore empty until the connector
  exposes top-scorers.
- **Roster freshness** uses the value-level `synced_at` on the
  `brasil-roster` doc (not the competition's `version_control`), so
  national-team rosters can be tracked independently of any league.
- **No odds**: this module is a pure data-acquisition layer.
  Connect an odds connector and a separate enrich-* workflow if odds
  are needed downstream.
