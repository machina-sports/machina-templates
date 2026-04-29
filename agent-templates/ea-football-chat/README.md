# ea-football-chat

Chat agent that answers football questions using live ESPN / Understat / FPL /
Transfermarkt data via the `sports-skills` Python library.

Supports: **Premier League, Serie A, La Liga, Bundesliga, Ligue 1, Champions League**.

---

## Architecture

```
User message
    │
    ▼
agent.yml          (orchestrator — chains all steps)
    │
    ▼ Step 1
chat-reasoning     (workflow + prompt)
    Classifies intent → { action, parameters }
    LLM: Gemini 2.5 Flash / Vertex AI
    │
    ▼ Step 2  (one branch runs, rest skipped via condition:)
get-league-standings   condition: action == "standings"
get-daily-fixtures     condition: action == "daily-fixtures"
get-upcoming-fixtures  condition: action == "upcoming-fixtures"
get-team-form          condition: action == "team-form"
get-team-schedule      condition: action == "team-schedule"
get-top-scorers        condition: action == "top-scorers"
search-entity          condition: action == "search-entity"
    │
    ▼ Step 3
chat-response      (workflow + prompt)
    Composes answer grounded in tool data
    LLM: Gemini 2.5 Flash / Vertex AI
```

---

## File layout

```
agent.yml                        Orchestrator
_install.yml                     Registration manifest (datasets load order)
_folders.yml                     Studio UI folder grouping

prompts/
  chat-reasoning.yml             Prompt dataset: intent classifier + JSON schema
  chat-response.yml              Prompt dataset: answer composer
  tool-catalog.yml               Reference (not loaded at runtime)

workflows/
  chat-reasoning.yml             Calls chat-reasoning prompt via invoke_prompt
  chat-response.yml              Calls chat-response prompt via invoke_prompt

tools/                           Each file is a workflow registered as a dataset
  get-league-standings.yml       get_current_season → get_season_standings
  get-daily-fixtures.yml         get_daily_schedule
  get-upcoming-fixtures.yml      get_current_season → get_season_schedule
  get-team-form.yml              search_team → get_team_schedule (last 5)
  get-team-schedule.yml          search_team → get_team_schedule (next 10)
  get-top-scorers.yml            get_current_season → get_season_leaders
  search-entity.yml              search_team + search_player
  get-match-report.yml           get_event_summary + get_event_statistics + get_event_xg

connectors/
  sports-skills.yml              Connector metadata (name, command, filetype=pyscript)
  sports_skills.py               Dispatcher: routes `command` param to sports_skills fn
```

---

## Platform prerequisites

1. **`google-genai` connector** configured on the target project — either
   AI Studio (`api_key`) or Vertex AI (`credential + project_id + location`).
   The workflows use `provider: vertex_ai, location: global`.

2. **`sports-skills` Python library** — the pyscript connector auto-installs it
   on first call via `pip install --target /tmp/sports_skills_pkg`.
   No manual install needed; the package is fetched at runtime.
   No API keys required — ESPN / Understat / FPL / Transfermarkt are public endpoints.

---

## Deploying / updating

```bash
# 1. Package from inside the template directory
cd agent-templates/ea-football-chat
zip -r /tmp/ea-football-chat.zip . -x "*.DS_Store" -x "__pycache__/*" -x "*.pyc"

# 2. Upload to pod
curl -s -X POST \
  "https://<org>-<pod>.org.machina.gg/templates/upload" \
  -H "X-Api-Token: <token>" \
  -F "file=@/tmp/ea-football-chat.zip"
```

---

## Testing

### Individual tool

```bash
# Correct: send inputs flat — /workflow/execute wraps the body internally
curl -X POST ".../workflow/execute/get-league-standings" \
  -H "Content-Type: application/json" \
  -d '{"competition_id": "premier-league"}'

# Wrong: double-nesting makes inputs evaluate to None
# -d '{"context-workflow": {"competition_id": "premier-league"}}'
```

### Full agent

```bash
curl -X POST ".../agent/executor/ea-football-chat" \
  -H "X-Api-Token: <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "context-agent": {
      "messages": [{"role": "user", "content": "How is Arsenal doing this season?"}],
      "league": "premier-league"
    },
    "agent-config": {"delay": false}
  }'
```

A healthy response has: `reasoning` (classified intent), `tool_result` (raw data), `result` (LLM answer).

---

## Connector calling convention (pyscript)

Machina calls `football(request_data)` where:
```python
request_data = {
    "connector_exec": "football",
    "headers": {...},
    "params": { ...task inputs... },   # inputs are HERE, not top-level
}
```

Must return:
```python
{"status": True,  "data": <payload>}
{"status": False, "data": {}, "error": {"code": N, "message": "..."}}
# error must be a dict — never a bool
```

pip install must use `--target /tmp/yourpkg` — container images are read-only (site-packages is not writable). Always expose pip errors via `subprocess.run(capture_output=True)` — never devnull stderr.

---

## `$` semantics in workflow YAML

| Location | `$` means |
|---|---|
| Task `outputs:` | `data` field of the connector/prompt response |
| Task `inputs:` | Accumulated workflow state (all prior task outputs merged) |
| Task `condition:` | Accumulated workflow state |
| Workflow `outputs:` | Accumulated workflow state |

Example:
```yaml
# task output: capture full data payload
outputs:
  standings: "$"           # standings = {"standings": [...]}

# workflow output: read that variable from state
outputs:
  result: "$.get('standings')"    # → {"standings": [...]}
```

---

## Supported task types in workflows

| Type | Supported |
|---|---|
| `connector` | ✓ |
| `prompt` | ✓ |
| `document` | ✓ |
| `mapping` | ✓ |
| `map` / `for-each` (iteration) | ✗ — silently unsupported, causes NoneType crash |

If you need to iterate over a list, return the list and let the LLM interpret it, or implement a `mapping` dataset.

---

## Known limitations

- **Top scorers**: `get_season_leaders` only works for Premier League at the current sports-skills version. Other leagues return null.
- **Champions League standings**: the UCL uses a league-phase table which may differ by season format.
- **Match xG**: only fetched for the 5 major leagues (not UCL) due to data availability.

---

## Prompt design decisions

### Reasoning (`chat-reasoning.yml`)

- **STEP 0 runs first**: detects follow-ups ("yeah", "give me the results", "same for La Liga") and carries over `competition_id` / `query` / `action` from conversation history before attempting keyword matching.
- **Competition carry-over**: if no league is mentioned in the new message, the previous league is reused — avoids resetting to the default league mid-conversation.
- **`general` is a last resort**: only used when neither the message nor conversation history contain any football topic. Ambiguous short messages always resolve via context.

### Response (`chat-response.yml`)

- **Scan before concluding**: `upcoming-fixtures` data contains both past and future events. The response prompt checks `status` per event — closed events are shown as results, not_started as fixtures. Never says "no upcoming matches" when past results are available.
- **Max 5 items**: all lists are capped at 5 to keep responses chat-sized.
- **No scores for future events**: only closed events show N–N scores.
- **Conversation-aware**: checks `_2-messages` before asking for clarification or declaring data unavailable.
