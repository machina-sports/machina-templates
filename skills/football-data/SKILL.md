# Football Data Skill

Read-side football data primitives backed by **API-Football**. Each
workflow is a thin wrapper over a single API-Football endpoint, normalised
to a stable shape so downstream UIs / agents don't need to know the
underlying provider.

## Requirements

- `connectors/api-football` installed in the same project.
- Vault credential `TEMP_CONTEXT_VARIABLE_API_FOOTBALL_API_KEY` set to a
  valid API-Football key. Without it every workflow returns the upstream
  403 / "Invalid API key" payload in `workflow-error`.

## Workflows

### `football-data-get-fixture`

Fetch one fixture by id.

```bash
machina workflow run football-data-get-fixture fixture_id=1208021
```

Inputs:
- `fixture_id` (int) — API-Football fixture id.

Output:
- `fixture` — `{id, date, status, venue, referee, league, teams, goals, score, lineups, events, statistics}`.

### `football-data-get-team-recent-form`

Last N matches for a team (default 5).

```bash
machina workflow run football-data-get-team-recent-form team_id=33 last=5
```

Output:
- `matches[]` — each item: `{fixture_id, date, status, league, home, away, goals}`.

### `football-data-get-head-to-head`

Last N meetings between two teams (default 5).

```bash
machina workflow run football-data-get-head-to-head team_a_id=33 team_b_id=34 last=5
```

Output:
- `matches[]` — same shape as `recent-form`.

### `football-data-get-projected-lineup`

Confirmed / projected lineups for a fixture. Returns `lineups: []` when
they have not been released yet — callers should render a placeholder
("Lineup not yet confirmed") rather than dropping the section.

```bash
machina workflow run football-data-get-projected-lineup fixture_id=1208021
```

Output:
- `lineups[]` — each item: `{team, formation, coach, startXI[], substitutes[]}`.

## Calling from a frontend

The workflows are designed to be consumed directly by a single-page app
through the Factory deploy proxy. From the browser:

```js
const { proxyUrl } = window.MACHINA_DEPLOY;
const res = await fetch(`${proxyUrl}/workflow/execute/football-data-get-fixture`, {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({ fixture_id: 1208021 }),
});
const { outputs } = await res.json();
```

Use `agent-templates/event-summary` (or `skills/match-stats-formatter`)
to render the result into broadcaster-ready prose.
