# Live Match Orchestrator

End-to-end content orchestrator for a single soccer fixture. Pass an
`event_id`, get pre-game, live, and post-match content the production
team's overlay or teleprompter can consume — markdown for humans, JSON
alongside for machines.

## What it produces, keyed to kickoff

| Phase  | Workflow                                    | Output                                                                                                   |
| ------ | ------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `pre`  | `live-match-orchestrator-pre-game-brief`    | Storylines, projected lineups, head-to-head, recent form. Teleprompter-ready markdown + structured JSON. |
| `live` | `live-match-orchestrator-live-tick`         | One card per new goal / red / sub / big chance since `since_minute`. Call repeatedly during the match.   |
| `post` | `live-match-orchestrator-post-match-recap`  | 3-paragraph wrap + 5 social-ready highlight quotes. Markdown + plain text + JSON.                        |

The agent `live-match-orchestrator-agent` is the single entry point —
it dispatches by `phase`.

## Editorial posture

- **White-label**: refers to "the broadcaster" / "the production team",
  never a specific operator.
- **Neutral**: no rooting, no partisan language.
- **Evidence-bound**: no stat, no goal, no quote that isn't in the
  fixture data. Predictions are not produced.

## How fixture resolution works

The caller passes `event_id` only. `sports-skills.football.get_event_summary`
returns the fixture envelope (both squad ids, competition, kickoff);
every downstream task hangs off that response. The caller does NOT
need to know the league or either lineup ahead of time.

## Running it

### One-shot (pre-game brief)

```bash
machina agent run live-match-orchestrator-agent \
  event_id=<event-id> phase=pre
```

### Live polling (scheduled loop)

The first tick passes `since_minute=0`. Each subsequent tick reuses
the previous tick's `latest_minute`:

```bash
# tick 1
machina agent run live-match-orchestrator-agent \
  event_id=<event-id> phase=live since_minute=0 --sync

# tick 2 (e.g. 30s later) — pass back `latest_minute` from tick 1
machina agent run live-match-orchestrator-agent \
  event_id=<event-id> phase=live since_minute=23 --sync
```

When called from a scheduler / cron, store `latest_minute` between runs
and pass it back as `since_minute` so each tick only emits cards for
events that happened since the last poll.

### Post-match recap

```bash
machina agent run live-match-orchestrator-agent \
  event_id=<event-id> phase=post competition_id=premier-league
```

`competition_id` is optional but unlocks the xG step for top-5 European
leagues (`premier-league`, `serie-a`, `la-liga`, `bundesliga`,
`ligue-1`). Outside those, the recap still works — it just leans on
the timeline + statistics without xG.

### From the frontend (Client API)

`POST /workflow/execute/live-match-orchestrator-pre-game-brief` with
`{ "event_id": "<id>" }` at the top level of the body. Same shape for
`-live-tick` (add `since_minute`) and `-post-match-recap` (optional
`competition_id`).

## Dependencies

- **`sports-skills` connector** — installed from
  `connectors/sports-skills`. Provides the `invoke_football` dispatcher
  that drives every data-fetch task. No API key required.
- **`google-genai` connector** — required for prompt invocation. Set
  `TEMP_CONTEXT_VARIABLE_VERTEX_AI_CREDENTIAL` and
  `TEMP_CONTEXT_VARIABLE_VERTEX_AI_PROJECT_ID` in the project vault.

## Output shapes

### Pre-game brief

```json
{
  "headline": "Manchester City host Arsenal in a top-of-table meeting",
  "storylines": [
    {
      "title": "Title race recalibrated",
      "body": "City's recent form has tightened the gap at the top...",
      "evidence_keys": ["home_recent_form", "away_recent_form"]
    }
  ],
  "projected_lineups": { "confirmed": false, "home": [...], "away": [...] },
  "head_to_head": [{ "date": "...", "competition": "...", "home": "...", "away": "...", "score": "..." }],
  "recent_form": { "home": [...], "away": [...] },
  "markdown": "## Manchester City host Arsenal in a top-of-table meeting\n\n### Storylines..."
}
```

### Live tick

```json
{
  "score": { "home": 1, "away": 0 },
  "status": { ... },
  "latest_minute": 23,
  "cards": [
    {
      "minute": "23",
      "event_type": "goal",
      "headline": "Haaland breaks the deadlock from the spot",
      "narrative": "Haaland converts from twelve yards after a VAR review confirms the penalty",
      "score_after": { "home": 1, "away": 0 },
      "players": ["E. Haaland"]
    }
  ]
}
```

### Post-match recap

```json
{
  "headline": "Manchester City edge Arsenal in a tight title showdown",
  "markdown": "## ...\n\nParagraph 1...\n\nParagraph 2...\n\nParagraph 3...",
  "text": "...",
  "highlight_quotes": [
    { "position": 1, "angle": "decisive_moment", "quote": "...", "evidence": "Haaland 23' penalty" },
    { "position": 2, "angle": "shape_of_the_game", "quote": "...", "evidence": "Arsenal 64% possession" }
  ]
}
```

## Why three workflows, not one prompt

Each phase has a different cadence (one-shot vs. polled vs. one-shot),
a different model choice (pro for narrative depth, flash for low-latency
live ticks), and a different output schema. Splitting into three
workflows keeps each one fast, observable, and individually re-runnable
— and lets the production team wire each phase into a different
scheduler / overlay without untangling a monolith.
