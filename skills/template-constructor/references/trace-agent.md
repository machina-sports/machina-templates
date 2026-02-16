---
description: Trace agent execution chain showing workflows, tasks, variable propagation, connectors, and documents
---

# DevOps: Trace Agent

Trace the complete execution chain of a Machina agent: from `context-agent` inputs, through each workflow (inputs/outputs/conditions), down to each task (type, connector, command, condition, inputs, outputs). Visualizes data flow and variable propagation for debugging.

**Difference from other skills:**
- `analyze-template` — static overview of **all** template components
- `validate-template` — checks YAML errors
- **`trace-agent`** — traces **one specific agent**, showing the execution chain with variable propagation

## Trigger

- `/mkn-templates:trace-agent`
- "Trace agent [path]"
- "Trace execution chain for [agent]"
- "Show variable flow for [agent]"

## Process

### 1. Identify Agent

Receive the agent YAML path or a template path + agent name.

**Option A** — Direct agent path:
```
/Users/fernando/machina/dazn-templates/agent-templates/dazn-coverage/refresh/agents/consumer.yml
```

**Option B** — Template path (discover agents):
```
agent-templates/dazn-coverage/refresh
```
If template path given, scan for agent files:
1. Look in `agents/*.yml`
2. Also check `_install.yml` datasets for `type: agent` entries
3. If multiple agents found, ask user to choose

**Known template repositories:**
- `/Users/fernando/machina/dazn-templates/agent-templates/`
- `/Users/fernando/machina/entain-templates/agent-templates/`
- `/Users/fernando/machina/machina-templates/agent-templates/`

### 2. Parse Agent YAML

Read the agent YAML file and extract:

| Field | YAML Path | Purpose |
|-------|-----------|---------|
| name | `agent.name` | Agent identifier |
| title | `agent.title` | Display name |
| description | `agent.description` | Purpose |
| status | `agent.context.status` | active/inactive |
| frequency | `agent.context.config-frequency` | Execution interval (minutes) |
| context-agent | `agent.context-agent` | Input parameters with defaults |
| workflows | `agent.workflows[]` | Execution steps |

For each workflow entry in the agent, extract:
- `name` — workflow reference name
- `description` — step description
- `condition` — execution condition (Python expression)
- `inputs` — variables passed into workflow
- `outputs` — variables received from workflow

### 3. Parse Workflow YAMLs

For each workflow referenced in the agent:

1. **Locate file**: Search in the same template directory structure:
   - `workflows/{name}.yml` (strip prefix if workflow name has a prefix)
   - `configs/{name}.yml`
   - Or search by glob: `**/*.yml` and match `workflow.name`
2. **Read and extract**:

| Field | YAML Path | Purpose |
|-------|-----------|---------|
| name | `workflow.name` | Workflow identifier |
| inputs | `workflow.inputs` | Input parameters |
| outputs | `workflow.outputs` | Return values |
| context-variables | `workflow.context-variables` | Credentials/API keys |
| tasks | `workflow.tasks[]` | Execution steps |

### 4. Parse Tasks

For each task in a workflow, extract based on type:

#### All task types:
- `type` — document, connector, prompt, mapping, function, agent
- `name` — task identifier
- `description` — purpose
- `condition` — execution condition
- `foreach` — iteration config (if present): `items`, `concurrent`

#### Type: `document`
- `config.action` — search, save, update, bulk-save, delete
- `filters` — document search/match criteria
- `documents` — document body for save/update
- `outputs` — result variables

#### Type: `connector`
- `connector.name` — connector identifier
- `connector.command` — function to call
- `inputs` — variables passed to connector
- `outputs` — variables received from connector

#### Type: `prompt`
- `connector` — LLM connector (google-genai, machina-ai, etc.)
- `inputs` — context for prompt
- `outputs` — generated content

#### Type: `mapping`
- `inputs` — source data
- `outputs` — transformed data

#### Type: `function`
- `code` — inline Python code
- `outputs` — computed variables

### 5. Build Summaries

After parsing all workflows and tasks, build three summary sections:

#### Connectors Used
Group by connector name:
- List all commands used
- For each command, note which step (workflow) uses it
- If connector YAML exists in the template, optionally read it to list total available commands

#### Documents Touched
Categorize by operation:
- **read** (search): document names used in `config.action: search`
- **write** (save/bulk-save): document names created
- **update**: document names modified
- Extract document names from `filters.name` or `documents.*` keys

#### Variable Chain
For each variable that flows between workflows:
- **Origin**: Which workflow/task first outputs it
- **Consumers**: Which workflows/tasks consume it as input
- **Conditions**: Which workflow conditions reference it
- Mark variables that are consumed (not passed further) vs propagated

### 6. Output Trace

Generate the trace in tree format. Follow this structure exactly:

```
AGENT: {agent-name}
  frequency: {N} min | status: {status}
  context-agent:
    {param}: {expression}

  ┌─ STEP 1: {workflow-name}
  │  condition: {condition or "(none)"}
  │  inputs:  {comma-separated input variable names}
  │  outputs: {comma-separated output variable names}
  │
  │  tasks:
  │    1. [{task-type-badge}]  {task-name}
  │       condition: {condition if present}
  │       {connector details if type=connector}
  │       → {output variables}
  │    2. [{task-type-badge}]  {task-name}
  │       → {output variables}
  │
  ├─ STEP 2: {workflow-name}
  │  condition: {condition}
  │  inputs:  {inputs}
  │  outputs: {outputs}
  │
  │  tasks:
  │    1. ...
  │
  ├─ STEP N-1: ...
  │
  └─ STEP N: {last-workflow-name}
     condition: {condition}
     inputs:  {inputs}
     ...tasks...

CONNECTORS USED:
  {connector-name} ({N} commands)
    - {command_name}  ← used by step {N}
    - {command_name}  ← used by step {N}

DOCUMENTS TOUCHED:
  read:   {doc-name}, {doc-name}
  write:  {doc-name}
  update: {doc-name}, {doc-name}

VARIABLE CHAIN:
  {var} → {origin-workflow} → {consumer-workflows} (or "consumed")
  {var} ← {origin-workflow} → {consumer-workflows, conditions}
```

**Task type badges:**
| Type | Badge |
|------|-------|
| document (search) | `[doc:search]` |
| document (save) | `[doc:save]` |
| document (update) | `[doc:update]` |
| document (bulk-save) | `[doc:bulk-save]` |
| document (delete) | `[doc:delete]` |
| connector | `[connector]` |
| prompt | `[prompt]` |
| mapping | `[mapping]` |
| function | `[function]` |
| agent | `[agent]` |

**Foreach annotation:** If a task has `foreach`, append `(foreach, concurrent)` or `(foreach)` to the badge line.

**Connector detail line:** For connector tasks, show:
```
connector: {connector-name} > {command}
inputs:  {input variable names}
```

## Example Trace

```
AGENT: coverage-refresh-consumer
  frequency: 2 min | status: inactive
  context-agent:
    force_competition_id: $.get('force_competition_id', None)

  ┌─ STEP 1: coverage-refresh-checkin-live
  │  condition: (none)
  │  inputs:  force_competition_id
  │  outputs: season_id, competition_id, competition_name, season_locked_live
  │
  │  tasks:
  │    1. [doc:search]  load-coverage-config
  │       → competitions
  │    2. [doc:search]  search-existing-seasons
  │       condition: len(competitions) > 0
  │       → existing_seasons
  │    3. [connector]   prepare-checkin-live
  │       connector: coverage-controller > invoke_prepare_checkin_live
  │       inputs:  existing_seasons, force_competition_id
  │       → selected_season, season_id, competition_id, competition_name
  │    4. [doc:update]  lock-selected-season-live
  │       condition: season_id != ''
  │       → season_locked_live
  │
  ├─ STEP 2: coverage-refresh-gateway-live
  │  condition: season_locked_live is True
  │  inputs:  season_id, competition_id
  │  outputs: has_live, has_closed
  │
  │  tasks:
  │    1. [doc:search]  search-season-fixtures
  │       condition: season_id != ''
  │       → season_fixtures, has_fixtures
  │    2. [connector]   evaluate-fixture-states
  │       connector: coverage-controller > invoke_evaluate_fixture_states
  │       inputs:  fixtures
  │       → has_live, has_closed
  │
  ├─ STEP 3: coverage-refresh-fixtures
  │  condition: season_locked_live is True
  │  inputs:  season_id, competition_id, competition_name
  │  outputs: fixtures_updated
  │
  │  tasks:
  │    1. [connector]   encode-season-id
  │       connector: coverage-controller > invoke_encode_season_id
  │       inputs:  season_id
  │       → encoded_season_id
  │    2. [doc:search]  search-existing-fixtures
  │       → existing_fixtures
  │    3. [connector]   fetch-sportradar-schedules
  │       connector: sportradar-soccer > invoke_get_season_schedules
  │       inputs:  encoded_season_id
  │       → schedules_raw
  │    4. [connector]   parse-schedules-to-iptc
  │       connector: coverage-sportradar-parser > invoke_parse_schedules_to_iptc
  │       condition: len(schedules_raw) > 0
  │       inputs:  schedules_raw, competition_id, competition_name, season_id
  │       → parsed_fixtures
  │    5. [connector]   detect-fixture-updates
  │       connector: coverage-controller > invoke_detect_fixture_updates
  │       condition: len(parsed_fixtures) > 0
  │       inputs:  parsed_fixtures, existing_fixtures
  │       → changed_fixtures, fixtures_updated
  │    6. [doc:update]  update-changed-fixtures  (foreach, concurrent)
  │       condition: len(changed_fixtures) > 0
  │       → (document updates)
  │    7. [doc:update]  update-season-fixtures-status
  │       condition: season_id != ''
  │       → (document updates)
  │
  ├─ STEP 4: coverage-refresh-standings
  │  condition: season_locked_live AND (has_live OR has_closed)
  │  ...tasks...
  │
  ├─ STEP 5: coverage-refresh-leaders
  │  condition: season_locked_live AND (has_live OR has_closed)
  │  ...tasks...
  │
  └─ STEP 6: coverage-refresh-checkout-live
     condition: season_locked_live is True
     inputs:  season_id
     ...tasks...

CONNECTORS USED:
  coverage-controller (3 commands)
    - invoke_prepare_checkin_live     ← used by step 1
    - invoke_encode_season_id        ← used by step 3
    - invoke_evaluate_fixture_states ← used by step 2
    - invoke_detect_fixture_updates  ← used by step 3
  coverage-sportradar-parser (1 command)
    - invoke_parse_schedules_to_iptc ← used by step 3
  sportradar-soccer (external)
    - invoke_get_season_schedules    ← used by step 3

DOCUMENTS TOUCHED:
  read:   dazn-coverage-config, dazn-season, sport:Event
  write:  (none)
  update: dazn-season (lock/unlock, version_content), sport:Event (status, scores)

VARIABLE CHAIN:
  force_competition_id → checkin-live → (consumed)
  season_id ← checkin-live → gateway, fixtures, standings, leaders, checkout
  competition_id ← checkin-live → gateway, fixtures, standings, leaders
  competition_name ← checkin-live → fixtures, standings, leaders
  season_locked_live ← checkin-live → conditions (steps 2-6)
  has_live ← gateway → conditions (steps 4-5)
  has_closed ← gateway → conditions (steps 4-5)
```

---

## Execution Mode

When the user asks to trace a **real execution** (mentions times, durations, status, failures, runtime, etc.), switch to execution mode. This mode queries the MCP server for actual execution data and overlays runtime information onto the static trace.

### Trigger (Execution Mode)

- `/mkn-templates:trace-agent --execution [agent-name]`
- "Trace last execution of [agent]"
- "Show execution times for [agent]"
- "What failed in the last run of [agent]?"
- Any trace-agent invocation that mentions: times, durations, status, failures, skips, runtime, performance

### E1. Select MCP Server

Ask user which environment to query:

| Environment | MCP Server Prefix |
|-------------|-------------------|
| DAZN Dev | `mcp__dazn-ros-dev__` |
| DAZN Staging | `mcp__dazn-ros-stg__` |
| SBot Dev | `mcp__sbot-dev__` |
| SBot Staging | `mcp__sbot-stg__` |
| SBot Prod | `mcp__sbot-prd__` |
| SIA Dev | `mcp__sia-dev__` |
| Mister AI Dev | `mcp__mister-ai-dev__` |

### E2. Find Agent Executions

Search recent executions for the agent:

```python
search_agent_executions(
    filters={"name": "{agent-name}"},
    sorters=["date", -1],
    page=1,
    page_size=5
)
```

**Compact results include**: `_id`, `name`, `status`, `date`, `finished_time`, `execution_time`, `execution_tokens`, `completed_workflows`, `total_workflows`

Present a list to the user:
```
Recent executions of coverage-refresh-consumer:
  1. 2026-02-14 10:32:15  completed  4/6 workflows  12.3s  1,240 tokens
  2. 2026-02-14 10:30:12  completed  6/6 workflows  28.7s  3,420 tokens
  3. 2026-02-14 10:28:10  error      2/6 workflows   5.1s    680 tokens
```

If only one execution or user says "latest", skip selection.

### E3. Get Full Agent Execution

Fetch full execution details:

```python
get_agent_execution(
    agent_id="{execution_id}",
    compact=False
)
```

**Full mode returns**: all fields including `workflows[]` array with each workflow's `run_id`, `status`, `execution_time`, and output values.

Extract from the agent execution:
- `status` — completed, error, timeout
- `date` / `finished_time` — start/end timestamps
- `execution_time` — total duration (seconds)
- `execution_tokens` — total tokens consumed
- `workflows[]` — list of workflow runs with their `run_id`

### E4. Get Full Workflow Executions

For each workflow in the agent execution, fetch task-level details:

```python
get_workflow_execution(
    workflow_id="{workflow_run_id}",
    compact=False
)
```

**Full mode returns**: `tasks[]` array with each task's status, execution_time, outputs, errors, and audit info.

Extract from each workflow execution:
- `name` — workflow name
- `status` — completed, skipped, error
- `execution_time` — workflow duration
- `execution_tokens` — tokens used
- `tasks[]` — each task with:
  - `name` — task identifier
  - `status` — executed, skipped, error
  - `execution_time` — task duration
  - `error` — error message (if failed)
  - Output values (from `workflow_output` or task outputs)

### E5. Build Execution Trace

Overlay runtime data onto the static tree structure. Use status badges and timing annotations.

**Status badges:**
| Status | Badge |
|--------|-------|
| completed | `OK` |
| skipped (condition false) | `SKIP` |
| error | `FAIL` |
| timeout | `TIMEOUT` |

### E6. Output Execution Trace

```
AGENT: {agent-name}  [RUN: {execution_id}]
  status: {status} | duration: {total_time}s | tokens: {total_tokens}
  started:  {date}
  finished: {finished_time}
  workflows: {completed}/{total}

  ┌─ STEP 1: {workflow-name}  [OK 3.2s]
  │  inputs:  {actual input values or variable names}
  │  outputs: {actual output values or variable names}
  │
  │  tasks:
  │    1. [doc:search]  load-coverage-config           OK   0.4s
  │       → competitions (3 items)
  │    2. [doc:search]  search-existing-seasons         OK   0.8s
  │       → existing_seasons (12 items)
  │    3. [connector]   prepare-checkin-live             OK   1.2s
  │       connector: coverage-controller > invoke_prepare_checkin_live
  │       → season_id="sr:season:118689", competition_id="sr:competition:17"
  │    4. [doc:update]  lock-selected-season-live        OK   0.8s
  │       → season_locked_live=True
  │
  ├─ STEP 2: {workflow-name}  [OK 1.5s]
  │  tasks:
  │    1. [doc:search]  search-season-fixtures           OK   1.1s
  │       → season_fixtures (180 items), has_fixtures=True
  │    2. [connector]   evaluate-fixture-states           OK   0.4s
  │       → has_live=True, has_closed=False
  │
  ├─ STEP 3: {workflow-name}  [OK 8.4s]
  │  tasks:
  │    1. [connector]   encode-season-id                  OK   0.1s
  │    2. [doc:search]  search-existing-fixtures           OK   1.2s
  │    3. [connector]   fetch-sportradar-schedules         OK   3.8s  ← slowest
  │    4. [connector]   parse-schedules-to-iptc            OK   0.6s
  │    5. [connector]   detect-fixture-updates             OK   0.3s
  │       → changed_fixtures (2 items), fixtures_updated=2
  │    6. [doc:update]  update-changed-fixtures             OK   1.8s  (foreach, 2 items)
  │    7. [doc:update]  update-season-fixtures-status       OK   0.6s
  │
  ├─ STEP 4: {workflow-name}  [SKIP]
  │  reason: condition not met (has_live=True but has_closed=False → standings require closed)
  │
  ├─ STEP 5: {workflow-name}  [SKIP]
  │  reason: condition not met
  │
  └─ STEP 6: {workflow-name}  [OK 0.9s]
     tasks:
       1. [doc:update]  unlock-season-live                OK   0.9s
          → season_unlocked_live=True

EXECUTION SUMMARY:
  total:     14.0s (3.2 + 1.5 + 8.4 + 0 + 0 + 0.9)
  tokens:    1,240
  workflows: 4/6 executed, 2 skipped
  tasks:     14/18 executed, 0 failed
  slowest:   fetch-sportradar-schedules (3.8s, step 3)
  bottleneck: step 3 (8.4s = 60% of total)
```

**Key annotations in execution mode:**

1. **Timing per task**: Right-aligned `OK 0.4s` after each task name
2. **Slowest task**: Mark with `← slowest` annotation
3. **Skip reason**: Show which condition evaluated false and why (include actual variable values)
4. **Error details**: For failed tasks, show the error message inline:
   ```
   3. [connector]   fetch-sportradar-schedules         FAIL  3.8s
      error: "HTTPError 429: Rate limit exceeded"
   ```
5. **Actual values**: When available from execution output, show real values instead of variable names:
   ```
   → season_id="sr:season:118689"   (instead of just → season_id)
   → season_fixtures (180 items)     (instead of just → season_fixtures)
   ```
6. **Foreach count**: Show actual iteration count: `(foreach, 2 items)` instead of just `(foreach)`
7. **Execution summary**: Bottom section with totals, bottleneck analysis, and skip/fail counts

### E7. Failure Analysis (if errors found)

If any workflow or task has status `error`, add a dedicated section:

```
FAILURES:
  step 3, task 3: fetch-sportradar-schedules
    status:  error
    time:    3.8s
    error:   "HTTPError 429: Rate limit exceeded"
    impact:  blocks tasks 4-7 in step 3 (parsed_fixtures never set)
    suggestion: Check SportRadar API rate limits / add retry logic
```

### E8. Performance Insights (optional)

If user asks for performance analysis, add:

```
PERFORMANCE:
  avg execution:  18.2s (last 10 runs)
  p95 execution:  32.1s
  most common skip: steps 4-5 (standings/leaders) — 72% of runs
  most common fail: fetch-sportradar-* — 3% of runs (rate limits)
  token efficiency: 1,240 tokens/run avg

TIMING BREAKDOWN:
  external API calls:  8.2s (58%)  ← sportradar-soccer
  document operations:  4.8s (34%)
  connector (internal): 2.0s (14%)
  overhead:             0.4s (3%)
```

This requires fetching multiple executions via `search_agent_executions` with `totals=True` and analyzing patterns.

## Example Execution Interaction

```
User: /mkn-templates:trace-agent --execution coverage-refresh-consumer

Claude: Which environment?
  1. DAZN Dev (Recommended)
  2. DAZN Staging

User: 1

Claude: [Searches recent executions]

Recent executions of coverage-refresh-consumer:
  1. 2026-02-14 10:32:15  completed  4/6  12.3s
  2. 2026-02-14 10:30:12  completed  6/6  28.7s
  3. 2026-02-14 10:28:10  error      2/6   5.1s

Which execution to trace?
  1. Latest (10:32:15)
  2. Full run (10:30:12)
  3. Failed run (10:28:10)

User: 3

Claude: [Fetches full execution + workflow details]
       [Outputs execution trace with FAIL annotations]
       [Adds FAILURES section with root cause analysis]
```

---

## Mode Summary

| Mode | Trigger | Data Source | Shows |
|------|---------|-------------|-------|
| **Static** (default) | agent YAML path | Local YAML files | Structure, variables, conditions |
| **Execution** | `--execution` or runtime keywords | MCP API | Times, status, failures, actual values |

Both modes use the same tree layout — execution mode adds runtime annotations on top.

---

## Tips

- Use **static mode** to understand agent design and variable flow before deploying
- Use **execution mode** to debug failures, find bottlenecks, and verify runtime behavior
- Look for **dead variables** — outputs that no downstream workflow consumes
- Check **conditions** — a workflow that never executes means all its outputs are empty
- Identify **external connectors** (sportradar-soccer, google-storage) vs **template connectors** (coverage-controller)
- Use with `foreach` tasks to understand batch processing scope
- Cross-reference with `context-variables` to identify **required credentials** per workflow
- Combine with `/mkn-templates:analyze-template` for full template overview + specific agent trace
- In execution mode, **slowest task** and **bottleneck step** help prioritize optimization

## Related

- [Analyze Template](./analyze-template.md) — Full template component overview
- [Validate Template](./validate-template.md) — YAML structure validation
- [Install Template](./install-template.md) — Install validated templates
