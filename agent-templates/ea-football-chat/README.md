# ea-football-chat

Chat agent that answers football questions using live ESPN / Understat / FPL /
Transfermarkt data. Designed for the EA Sports Hub demo (`factory-kfhagq0m.machina.gg`).

## Architecture

- **`agent.yml`** — 3-step agent: `chat-reasoning` → `map(tool_calls)` → `chat-response`.
- **`prompts/`** — `chat-reasoning` picks tools + params; `chat-response` writes the reply; `tool-catalog` is a reference catalog.
- **`workflows/`** — `chat-reasoning` (router) + `chat-response` (google-genai call).
- **`tools/`** — 6 tool workflows each calling the `sports-skills` connector via the `football` dispatcher, plus `diag-ping` for runtime health checks.
- **`connectors/sports-skills.{yml,py}`** — pyscript connector exposing a single `football` command that dispatches on the inner `command` input to the matching `sports_skills.football._connector` function.

## Framework contract (reverse-engineered)

The Machina pyscript connector invoker follows a strict contract — mismatches show up as opaque `'bool' object has no attribute 'get'` errors. The fields discovered via `diag-ping` probing:

**Request shape.** Pyscript functions receive `request_data = {"params": {...}, "headers": {}, "connector_exec": "<command>", "path_attribute": {}, "server_params": {}}`. The task's `inputs:` block lands inside `request_data["params"]`. Always read via `request_data.get("params")`, not flat access.

**Response shape.** The response must be a dict with `status: True|False` and `data: <dict>`. The framework strips every other top-level key (including `result`, `message`, `payload`) and exposes only the `data` value as `$` inside the task's `outputs:` block.

**Tool pattern.** Read library fields directly from `$`:

```yaml
- type: connector
  name: get_standings
  connector: { name: sports-skills, command: football }
  inputs:
    command: "'get_season_standings'"
    season_id: "$.get('season_id')"
  outputs:
    standings: "$.get('standings')"   # library returns {"standings": [...]}
```

## Platform prerequisites

1. **`sports-skills` Python library on the pyscript runtime.** The connector does `from sports_skills.football import _connector`. If missing, `diag-ping` reports `lib_check.import_ok: false`. Install on the client-api pod:
   ```
   kubectl exec -it <client-api-pod> -- pip install sports-skills
   ```
   For a persistent fix, add `sports-skills` to the pyscript runtime image's requirements.
2. **`google-genai` connector** configured on the project. The `chat-response` workflow currently uses `invoke_chat` with `gemini-2.5-flash`.

No API keys are required for the sports data — ESPN / Understat / FPL / Transfermarkt are all public endpoints the library hits directly.

## Installing into a project

```bash
machina template install agent-templates/ea-football-chat -b <branch> -p <project-id>
```

Verify:

```bash
# 1. Connector registered with "Football" command
machina connector get sports-skills -p <project-id>

# 2. Dispatcher is alive + sports-skills library is importable
machina workflow run diag-ping -p <project-id> --json
# Expect: ping="pong", lib_check.import_ok=true, football_module_ok=true

# 3. End-to-end tool
machina workflow run get-daily-fixtures -p <project-id> --json

# 4. Agent
machina agent run ea-football-chat \
  messages='[{"role":"user","content":"Show me the Premier League table"}]' \
  -p <project-id>
```

## Related fix: OpenAI 401 invalid_organization

Shipped in the same initial PR, unrelated to this template: the `machina-ai`
connector's `invoke_prompt` / `invoke_embedding` accept optional `organization`
and `project` params — routed through `default_headers={"OpenAI-Project": ...}`.
Projects hitting `401 invalid_organization` with `sk-proj-*` keys can unblock
via workflow `context-variables`:

```yaml
context-variables:
  machina-ai:
    api_key: $TEMP_CONTEXT_VARIABLE_SDK_OPENAI_API_KEY
    organization: $TEMP_CONTEXT_VARIABLE_SDK_OPENAI_ORG_ID
    project: $TEMP_CONTEXT_VARIABLE_SDK_OPENAI_PROJECT_ID
```
