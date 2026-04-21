# ea-football-chat

Chat agent that answers football questions using live ESPN / Understat / FPL /
Transfermarkt data. Designed for the EA Sports Hub demo (`factory-kfhagq0m.machina.gg`)
and portable to any project whose platform has `google-genai` configured.

## Architecture

- **`agent.yml`** — 3-step agent: `chat-reasoning` → `map(tool_calls)` → `chat-response`.
- **`prompts/`** — `chat-reasoning` picks tools + params; `chat-response` writes the reply; `tool-catalog` is reference.
- **`workflows/`** — `chat-reasoning` (router) + `chat-response` (LLM call).
- **`tools/`** — 6 tool workflows each calling the `sports-skills` connector via the `football` dispatcher.
- **`connectors/sports-skills.{yml,py}`** — pyscript connector with a single `football` command that dispatches on the `command` input to the corresponding `sports_skills.football._connector` function.

The dispatcher interface matches what the 6 tools already call:

```yaml
connector:
  name: sports-skills
  command: football
inputs:
  command: "'get_season_standings'"
  season_id: "$.get('season_id')"
```

Allowed inner `command` values: `get_current_season`, `get_competitions`,
`get_competition_seasons`, `get_season_schedule`, `get_season_standings`,
`get_season_leaders`, `get_season_teams`, `search_team`, `search_player`,
`get_team_profile`, `get_team_schedule`, `get_daily_schedule`,
`get_event_summary`, `get_event_lineups`, `get_event_statistics`,
`get_event_timeline`, `get_event_xg`, `get_event_players_statistics`,
`get_head_to_head`, `get_missing_players`, `get_season_transfers`,
`get_player_profile`, `get_player_season_stats`.

## Platform prerequisites

1. **`sports-skills` Python library available in the pyscript runtime.** The
   connector does `from sports_skills.football import _connector`. Confirm
   the platform runtime has it installed (`pip install sports-skills` — see
   <https://pypi.org/project/sports-skills/>). If the connector returns
   `{"error": True, "message": "sports-skills not installed: ..."}`, the
   runtime image is missing the dependency.
2. **`google-genai` connector configured** on the target project — either
   AI Studio (api_key) or Vertex AI (credential + project_id). The
   `chat-response` workflow currently uses `invoke_chat` with
   `gemini-2.5-flash`.

No API keys are required for the sports data itself — ESPN / Understat /
FPL / Transfermarkt are all public endpoints the library hits directly.

## Installing into a project

Studio-side, once per project:

1. **Import `_install.yml`.** Datasets install in order — connector first,
   then agent, then prompts, then workflows, then tools.
2. **Verify the connector landed.** The project should show a `sports-skills`
   connector with a single `Football` command. If an older `sports-skills`
   reference exists from a prior attempt, remove it first so the tools
   resolve to this one.
3. **Smoke-test a tool** via Studio's run-workflow UI:
   - `get-league-standings` with `competition_id: "premier-league"` — expect
     `workflow-status: true` and a populated `result.standings`.
   - `get-daily-fixtures` with no params — expect today's matches.
   - `search-entity` with `query: "Arsenal"` — expect team + player matches.
4. **Smoke-test the agent** with `{ messages: [{ role: "user", content:
   "Who's top of the Premier League?" }] }` — expect `chat-reasoning` to
   emit `tool_calls: [{tool: "get-league-standings", args: {competition_id:
   "premier-league"}}]`, the map step to fetch the table, and
   `chat-response` to return a prose summary.

## Related fix: OpenAI 401 invalid_organization

Unrelated to this template but shipped in the same PR: the `machina-ai`
connector's `invoke_prompt` / `invoke_embedding` now accept optional
`organization` and `project` params. Projects hitting `401 invalid_organization`
with `sk-proj-*` keys can fix it via workflow `context-variables`:

```yaml
context-variables:
  machina-ai:
    api_key: $TEMP_CONTEXT_VARIABLE_SDK_OPENAI_API_KEY
    organization: $TEMP_CONTEXT_VARIABLE_SDK_OPENAI_ORG_ID
    project: $TEMP_CONTEXT_VARIABLE_SDK_OPENAI_PROJECT_ID
```

No connector rebuild needed.
