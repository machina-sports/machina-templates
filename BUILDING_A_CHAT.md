# Building a Machina Chat Agent from Zero

This guide covers every layer of a production Machina chat agent: file structure, each component type, the pyscript connector calling convention, deployment, and testing. The `ea-football-chat` template is used as the reference throughout.

---

## 1. Repositories involved

| Repository | Role | What you change |
|---|---|---|
| `machina-templates` | The only repo you write code in. Contains the template zip that gets uploaded to a pod. | Everything: agent, workflows, prompts, tools, connectors |
| `machina-client-api` | Platform source — read only for debugging execution internals. | Nothing (unless you're fixing the platform itself) |
| `machina-k8-ui` | Kubernetes UI for managing pods, pods health, and Studio. | Nothing (used for pod setup/monitoring) |

---

## 2. Template folder structure

```
agent-templates/<your-chat>/
├── agent.yml                    # Orchestrator: chains workflows together
├── _install.yml                 # Registration: lists every file to load on deploy
├── _folders.yml                 # Studio UI: organizes files into folders
│
├── workflows/
│   ├── chat-reasoning.yml       # Step 1 — classifies intent, calls an LLM prompt
│   └── chat-response.yml        # Step 3 — generates the final answer
│
├── prompts/
│   ├── chat-reasoning.yml       # Prompt dataset: instruction + JSON schema for reasoning
│   └── chat-response.yml        # Prompt dataset: instruction for composing the answer
│
├── tools/                       # Each file is a workflow acting as a "tool"
│   ├── get-league-standings.yml
│   ├── get-daily-fixtures.yml
│   ├── get-team-form.yml
│   └── …
│
└── connectors/
    ├── sports-skills.yml        # Connector metadata (name, command, filetype)
    └── sports_skills.py         # Pyscript connector — Python executed at runtime
```

---

## 3. Execution flow

```
User message
    ↓
agent.yml
    ↓ Step 1
chat-reasoning workflow  →  chat-reasoning prompt (LLM)
    ↓ Returns JSON: { action, parameters }
agent.yml evaluates conditions on action
    ↓ Step 2 (one workflow runs, others are skipped)
get-league-standings / get-team-form / get-daily-fixtures / …
    ↓ each tool calls the pyscript connector → returns real data
    ↓ Step 3
chat-response workflow  →  chat-response prompt (LLM, grounded on tool data)
    ↓
Final answer
```

---

## 4. Component by component

### 4.1 `agent.yml` — the orchestrator

```yaml
agent:
  name: ea-football-chat
  title: "EA Sports Hub Football Chat"
  description: "Football chat covering PL, Serie A, La Liga, Bundesliga, Ligue 1, UCL."

  context-agent:              # Declares what inputs the agent accepts
    messages: $.get('messages', [])
    league: $.get('league', 'premier-league')

  workflows:

    - name: chat-reasoning    # Step 1: always runs
      inputs:
        messages: $.get('messages', [])
        league: $.get('league', 'premier-league')
      outputs:
        reasoning: $.get('reasoning', {})

    - name: get-league-standings   # Step 2a: runs only if reasoning says 'standings'
      condition: $.get('reasoning', {}).get('action') == 'standings'
      inputs:
        competition_id: $.get('reasoning', {}).get('parameters', {}).get('competition_id', $.get('league'))
      outputs:
        tool_result: $.get('result')

    # … other tool workflows with their conditions …

    - name: chat-response     # Step 3: always runs
      inputs:
        messages: $.get('messages', [])
        league: $.get('league', 'premier-league')
        reasoning: $.get('reasoning', {})
        tool_result: $.get('tool_result')
      outputs:
        result: $.get('message', '')
        workflow-status: "'executed'"
```

**Key rules:**
- `$` in `inputs/outputs` of `agent.yml` = accumulated agent state (all previous outputs).
- `condition:` on a workflow step uses the same `$` context and must evaluate to a truthy Python expression.
- The agent state is flat — all workflow outputs are merged into one dict.

---

### 4.2 Reasoning workflow + prompt

**`workflows/chat-reasoning.yml`**

```yaml
workflow:
  name: chat-reasoning
  inputs:
    messages: "$.get('messages', [])"
    league: "$.get('league', 'premier-league')"
  outputs:
    reasoning: "$.get('reasoning', {})"
    workflow-status: "'executed'"
  tasks:
    - type: prompt
      name: ea-football-chat-reasoning       # Must match the prompt dataset name
      description: "Classify user intent."
      connector:
        name: google-genai
        command: invoke_prompt
        model: gemini-2.5-flash
        location: global
        provider: vertex_ai
      inputs:
        _1-league: "$.get('league')"          # _N- prefix → {{ _N-key }} in prompt template
        _2-messages: "$.get('messages', [])"
      outputs:
        reasoning: $                           # $ here = the JSON object returned by the schema
```

**`prompts/chat-reasoning.yml`**

```yaml
prompts:
  - type: prompt
    name: ea-football-chat-reasoning
    title: "EA Football Chat Reasoning"
    description: "Classifies user intent and extracts typed parameters."
    instruction: |
      Analyze the user's latest message from _2-messages.
      The user's default league preference is _1-league.
      … (your decision tree) …
    schema:                                    # Forces structured JSON output
      title: "EAFootballChatReasoning"
      type: "object"
      required: [action, parameters]
      properties:
        action:
          type: "string"
          enum: [standings, daily-fixtures, upcoming-fixtures, team-form, team-schedule, top-scorers, search-entity, general]
        parameters:
          type: "object"
          properties:
            competition_id:
              type: "string"
              enum: [premier-league, serie-a, la-liga, bundesliga, ligue-1, champions-league]
            query:
              type: "string"
```

**Prompt template conventions:**
- Input variables use `_1-`, `_2-`, `_3-` prefixes in the `inputs:` block.
- Inside the `instruction:` text, reference them as `{{ _1-league }}`, `{{ _2-messages }}`, etc.
- The `schema:` block forces the LLM to return a structured JSON object. The output task expression `$` captures that object directly.
- When the workflow outputs `reasoning: $`, the `$` in a `type: prompt` task output = the root of the schema object.

---

### 4.3 Response workflow + prompt

**`workflows/chat-response.yml`**

```yaml
workflow:
  name: chat-response
  inputs:
    messages: "$.get('messages', [])"
    league: "$.get('league', 'premier-league')"
    reasoning: "$.get('reasoning', {})"
    tool_result: "$.get('tool_result')"
  outputs:
    message: "$.get('message', '')"
    workflow-status: "'executed'"
  tasks:
    - type: prompt
      name: ea-football-chat-response
      connector:
        name: google-genai
        command: invoke_prompt
        model: gemini-2.5-flash
        location: global
        provider: vertex_ai
      inputs:
        _1-league: "$.get('league', 'premier-league')"
        _2-messages: "$.get('messages', [])"
        _3-reasoning: "$.get('reasoning', {})"
        _4-tool_result: "$.get('tool_result')"
      outputs:
        message: "$.get('choices', [{}])[0].get('message', {}).get('content', '')"
```

**Key:** The response prompt does NOT use a `schema:` block (or uses the `ChatCompletions` schema). That means the LLM returns free text extracted via `choices[0].message.content`.

---

### 4.4 Tool workflows

Each tool is a regular `workflow` YAML that lives in `tools/`. They are registered as workflows in `_install.yml`. The agent calls them by name in `agent.yml`.

**Pattern: single connector call**

```yaml
workflow:
  name: get-league-standings
  inputs:
    competition_id: "$.get('competition_id')"
  outputs:
    result: "$.get('standings')"             # standings = what the task put in state
    workflow-status: "$.get('standings') is not None"
  tasks:
    - type: "connector"
      name: "get_current_season"
      connector:
        name: "sports-skills"
        command: "football"
      inputs:
        command: "'get_current_season'"
        competition_id: "$.get('competition_id')"
      outputs:
        season_id: "$.get('season', {}).get('id')"   # $ = data field of connector response

    - type: "connector"
      name: "get_season_standings"
      condition: "$.get('season_id') is not None"    # $ = accumulated workflow state
      connector:
        name: "sports-skills"
        command: "football"
      inputs:
        command: "'get_season_standings'"
        season_id: "$.get('season_id')"
      outputs:
        standings: "$"                               # $ = full data dict from connector
```

**`$` semantics — the most important rule:**

| Context | `$` means |
|---|---|
| Task `outputs:` | `data` field of the connector/prompt response |
| Task `inputs:` | Accumulated workflow state (all prior task outputs) |
| Task `condition:` | Accumulated workflow state |
| Workflow `outputs:` | Accumulated workflow state |

So `standings: "$"` in task outputs captures the entire `data` payload. Then `$.get('standings')` in the workflow outputs reads the `standings` variable from state.

**Supported task types:**
- `connector` — calls a registered connector (pyscript, HTTP, etc.)
- `prompt` — calls an LLM prompt dataset via `invoke_prompt`
- `document` — document processing
- `mapping` — runs a registered mapping dataset

> ⚠️ `type: map` (iteration) is **NOT** supported in workflow tasks. If you need to process a list, return the list and let the LLM interpret it, or use a `mapping` dataset.

---

### 4.5 Pyscript connector

The connector is a Python file that Machina `exec()`s and then calls by command name.

**`connectors/sports_skills.py`**

```python
"""
Machina passes: request_data = {
    "connector_exec": "football",
    "headers": {...},
    "params": { ...task inputs... },   # <-- inputs are here, not top-level
}
Must return:
    {"status": True,  "data": <payload>}
    {"status": False, "data": {}, "error": {"code": N, "message": "..."}}
"""
from __future__ import annotations
import os, sys, subprocess

_CUSTOM_PATH = "/tmp/sports_skills_pkg"   # writable even in read-only container images

_ALLOWED = {
    "get_current_season",
    "get_season_standings",
    "get_season_leaders",
    "search_team",
    "get_team_schedule",
    "get_daily_schedule",
    # … full list …
}

def _get_connector():
    if os.path.isdir(_CUSTOM_PATH) and _CUSTOM_PATH not in sys.path:
        sys.path.insert(0, _CUSTOM_PATH)
    try:
        from sports_skills.football import _connector
        return _connector
    except ImportError:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "sports-skills>=0.4.0",
             "--target", _CUSTOM_PATH, "-q", "--no-cache-dir"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"pip install failed (exit {result.returncode}): {result.stderr.strip()[:500]}"
            )
        if _CUSTOM_PATH not in sys.path:
            sys.path.insert(0, _CUSTOM_PATH)
        from sports_skills.football import _connector
        return _connector

def football(request_data):          # Function name must match the command in sports-skills.yml
    task_inputs = request_data.get("params", {})   # Inputs are under "params"
    command = task_inputs.get("command")
    if not command:
        return {"status": False, "data": {}, "error": {"code": 400, "message": "'command' required"}}
    if command not in _ALLOWED:
        return {"status": False, "data": {}, "error": {"code": 400, "message": f"Unknown: {command}"}}
    try:
        _connector = _get_connector()
    except Exception as exc:
        return {"status": False, "data": {}, "error": {"code": 500, "message": str(exc)}}
    fn = getattr(_connector, command, None)
    if fn is None:
        return {"status": False, "data": {}, "error": {"code": 404, "message": f"Not found: {command}"}}
    forwarded = {k: v for k, v in task_inputs.items() if k != "command"}
    try:
        data = fn({"params": forwarded})
    except Exception as exc:
        return {"status": False, "data": {}, "error": {"code": 500, "message": str(exc)}}
    return {"status": True, "data": data}
```

**`connectors/sports-skills.yml`**

```yaml
connector:
  name: "sports-skills"
  description: "Football data via the sports-skills Python library."
  filename: "sports_skills.py"
  filetype: "pyscript"
  commands:
    - name: "Football"
      value: "football"        # This must match the Python function name
```

**Critical pyscript rules:**
1. Machina calls `football(request_data)` — the function name matches `command.value` in the YAML.
2. Task inputs land at `request_data["params"]`, not at the top level.
3. Return `{"status": True, "data": ...}` on success, `{"status": False, "data": {}, "error": {"code": N, "message": "..."}}` on error. `error` must be a `dict`, never a `bool`.
4. Container images are read-only — pip install must use `--target /tmp/yourpkg`, not the default site-packages.
5. Expose real pip errors: use `subprocess.run(capture_output=True)` and read `result.stderr`, never devnull.

---

### 4.6 `_install.yml` — registration

Lists every file that gets loaded when the template is installed on a pod.

```yaml
setup:
  title: "EA Sports Hub Football Chat"
  description: "…"
  category: [custom-templates]
  value: "agent-templates/ea-football-chat"
  version: 1.0.0

datasets:
  - type: "connector"
    path: "connectors/sports-skills.yml"
  - type: "agent"
    path: "agent.yml"
  - type: "prompts"
    path: "prompts/chat-reasoning.yml"
  - type: "prompts"
    path: "prompts/chat-response.yml"
  - type: "workflow"
    path: "workflows/chat-reasoning.yml"
  - type: "workflow"
    path: "workflows/chat-response.yml"
  - type: "workflow"
    path: "tools/get-league-standings.yml"
  # … all tool workflows …
```

Order matters: `connector` before `agent`, prompts before workflows that call them.

---

## 5. Deployment

### 5.1 Package

```bash
cd agent-templates/<your-chat>
zip -r /tmp/<your-chat>.zip . -x "*.DS_Store" -x "__pycache__/*" -x "*.pyc"
```

### 5.2 Upload to pod

```bash
curl -s -X POST \
  "https://<org>-<pod>.org.machina.gg/templates/upload" \
  -H "X-Api-Token: <token>" \
  -F "file=@/tmp/<your-chat>.zip"
```

The response lists what was updated. Each `"status": true` entry confirms a component loaded successfully.

---

## 6. Testing

### 6.1 Test a single tool workflow

The `/workflow/execute/<name>` route wraps the body it receives in `context-workflow` internally. Send inputs flat — **do not** wrap them yourself:

```bash
# Correct
curl -X POST "…/workflow/execute/get-league-standings" \
  -H "Content-Type: application/json" \
  -d '{"competition_id": "premier-league"}'

# Wrong — inputs become double-nested and evaluate to None
curl -X POST "…/workflow/execute/get-league-standings" \
  -H "Content-Type: application/json" \
  -d '{"context-workflow": {"competition_id": "premier-league"}}'
```

Check `workflow-status` and `result` in the response.

### 6.2 Test the full agent

```bash
curl -X POST "…/agent/executor/ea-football-chat" \
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

A working response includes: `reasoning` (classified intent), `tool_result` (raw data), and `result` (LLM-generated answer).

### 6.3 Diagnosing failures

| Symptom | Likely cause |
|---|---|
| `workflow-status: false`, no `workflow-error` | A condition evaluated to False (e.g., `season_id` is None, or the wrong input key was used) |
| `workflow-error: {message: "sports-skills install failed…"}` | pip install failed — check the error message, use `--target /tmp/` |
| `workflow-error: {message: "'bool' object has no attribute 'get'"}` | Connector returned `{"error": True}` instead of `{"error": {"code": …, "message": "…"}}` |
| `result: null`, no error | Tool ran but the output expression doesn't match the actual data keys — print/log the raw response to inspect |
| `Error: 'NoneType' object is not iterable` | An unsupported task type (e.g., `type: map`) was used; the output expression ran against the previous task's data |
| Inputs all `None` | Body sent to `/workflow/execute` was wrapped in `context-workflow` — send flat JSON instead |

---

## 7. Key gotchas summary

1. **`$` in task outputs ≠ `$` in task inputs.** Outputs: `data` from connector. Inputs and conditions: workflow state.
2. **Only 4 task types work:** `connector`, `prompt`, `document`, `mapping`. `type: map` is silently unsupported.
3. **pip install must use `--target /tmp/something`.** Container image is read-only; default site-packages install fails.
4. **`error` in connector response must be a dict**, not `True`/`False`. `error_info.get('message')` will crash if `error_info` is a bool.
5. **`/workflow/execute` wraps the body.** Send inputs flat. `/workflow/executor` and `/agent/executor` take `context-workflow`/`context-agent` wrappers.
6. **prompt task inputs use `_N-` prefixes.** `_1-league`, `_2-messages` become `{{ _1-league }}`, `{{ _2-messages }}` in the instruction template.
7. **Prompt + schema → `$` = root JSON object.** No need for `choices[0].message.content` extraction — the schema output is directly available via `$.get('field')`.
8. **sports_skills (and similar Python packages) call convention:** `fn({"params": {...}})` — always wrap forwarded inputs in a `params` key.
