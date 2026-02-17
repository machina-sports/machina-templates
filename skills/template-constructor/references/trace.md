# Trace

Trace the execution chain of any Machina entity — from skill down to individual task inputs/outputs. Visualizes data flow and variable propagation for debugging.

**Difference from other references:**
- `analyze` — static overview of **all** template components
- `validate` — checks YAML errors
- **`trace`** — traces **one specific entity**, showing execution chain with variable propagation

## Trigger

- `/mkn-templates:trace-agent`
- "Trace agent", "Trace workflow", "Trace skill", "Show variable flow", "Show input/output chain"

## Entry Points

Trace can start from any level. Each level expands downward:

```
Skill → Agent → Workflow → Task → Input/Output
```

| User Says | Start From |
|-----------|------------|
| "Trace skill X" | Skill (entry points → agents/workflows → tasks) |
| "Trace agent X" | Agent (context-agent → workflows → tasks) |
| "Trace workflow X" | Workflow (inputs → tasks → outputs) |
| "Trace document X" | Document (which workflows read/write this document) |
| "Trace input/output of X" | Variable chain (origin → consumers → conditions) |

---

## Skill Trace

### Process

1. Read `skill.yml` and extract fields per [skill.md](../schemas/skill.md): name, description, references, entry points (workflows and/or agents)
2. For each **workflow entry point**: trace as Workflow Trace (below)
3. For each **agent entry point**: trace as Agent Trace (below)
4. List all references with their `reference_id`

### Output

```
SKILL: {skill-name}
  version: {version} | status: {status}
  category: {categories}
  domain: {domain}

  references:
    - {reference_id}: {title}
    - {reference_id}: {title}

  entry points:

    [workflow] {workflow-name}
      inputs:  {comma-separated input names with defaults}
      outputs: {comma-separated output names}

    [agent] {agent-name}
      inputs:  {comma-separated input names with defaults}
      outputs: {comma-separated output names}
```

Then expand each entry point using the Agent Trace or Workflow Trace format below.

---

## Agent Trace

### Process

1. **Identify agent**: Receive agent YAML path or template path + agent name
   - **Direct path**: `{repo}/agent-templates/{template-name}/agents/{agent}.yml`
   - **Discover**: Look in `agents/*.yml` or `_install.yml` for `type: agent` entries
2. **Parse agent YAML** per [agent.md](../schemas/agent.md): name, title, status, frequency, context-agent, context-variables, workflows list
3. **For each workflow**: name, description, condition, inputs, outputs
4. **Expand each workflow** using the Workflow Trace format below

### Output

```
AGENT: {agent-name}
  frequency: {N} min | status: {status}
  context-agent:
    {param}: {expression}

  context-variables:
    {connector-name}:
      {key}: {value-or-secret-ref}

  ┌─ STEP 1: {workflow-name}
  │  condition: {condition or "(none)"}
  │  inputs:  {comma-separated input variable names}
  │  outputs: {comma-separated output variable names}
  │
  │  tasks:
  │    1. [{task-type-badge}]  {task-name}
  │       inputs:  {key}: {expression}
  │       outputs: {key}: {expression}
  │       condition: {condition if present}
  │       {connector details if type=connector}
  │    2. [{task-type-badge}]  {task-name}
  │       inputs:  {key}: {expression}
  │       outputs: {key}: {expression}
  │
  ├─ STEP 2: {workflow-name}
  │  ...
  │
  └─ STEP N: {last-workflow-name}
     ...
```

---

## Workflow Trace

### Process

1. **Identify workflow**: Receive workflow YAML path or name
2. **Parse workflow YAML** per [workflow.md](../schemas/workflow.md): name, inputs, outputs, context-variables, tasks
3. **Parse each task** based on type:
   - **All types**: type, name, description, condition, foreach, inputs, outputs
   - **document**: config.action, filters, document_name, documents, metadata — per [document.md](../schemas/document.md)
   - **connector**: connector.name, connector.command
   - **prompt**: connector config (name, command, model)
   - **mapping**: input/output transformation

### Output

```
WORKFLOW: {workflow-name}
  context-variables:
    {connector-name}:
      {key}: {value-or-secret-ref}

  inputs:
    {key}: {expression}
  outputs:
    {key}: {expression}

  tasks:
    1. [{task-type-badge}]  {task-name}
       condition: {condition if present}
       foreach: {items-expression} {concurrent?}
       inputs:
         {key}: {expression}
       outputs:
         {key}: {expression}

    2. [{task-type-badge}]  {task-name}
       connector: {name} > {command}
       inputs:
         {key}: {expression}
       outputs:
         {key}: {expression}

    3. [{task-type-badge}]  {task-name}
       document_name: {collection}
       filters:
         {key}: {expression}
       outputs:
         {key}: {expression}
```

---

## Document Trace

Reverse trace: find all workflows that interact with a specific document.

### Process

1. **Identify document**: Receive document name (e.g., `sport:Event`, `thread`)
2. **Scan all workflow YAMLs** in the template for `type: document` tasks
3. **Match** tasks where `document_name`, `filters.name`, or `filters.document_id` references the target document
4. **Categorize** each match by operation

### Output

```
DOCUMENT: {document-name}

  READERS (search):
    - {workflow-name} > task {N}: {task-name}
      filters: {filter-expression}
      outputs: {extracted-fields}

  WRITERS (save/bulk-save):
    - {workflow-name} > task {N}: {task-name}
      documents: {data-expression}
      metadata: {metadata-fields}
      embed-vector: {true/false}

  UPDATERS (update/bulk-update):
    - {workflow-name} > task {N}: {task-name}
      filters: {match-expression}
      documents: {update-expression}

  DELETERS (delete):
    - {workflow-name} > task {N}: {task-name}
      filters: {match-expression}
```

---

## Input/Output Trace

Trace the lifecycle of a specific variable across the entire execution chain.

### Process

1. **Identify variable**: Receive variable name (e.g., `fixtures`, `thread_id`, `api_key`)
2. **Scan all YAMLs** (agent context-agent, workflow inputs/outputs, task inputs/outputs, conditions)
3. **Build chain**: origin → transformations → consumers

### Output

```
VARIABLE: {variable-name}

  ORIGIN:
    {entity-type}: {entity-name}
      {field}: {expression}

  CHAIN:
    1. {workflow-name} > {task-name} (outputs)
       {variable}: {expression}
    2. {workflow-name} > {task-name} (inputs)
       {variable}: {expression}
    3. {workflow-name} (condition)
       {condition-expression}

  DEAD: {true/false}
    (true if no downstream consumer reads this variable)
```

---

## Summaries

After any trace, append these summary sections when relevant:

### Connectors Used

```
CONNECTORS USED:
  {connector-name} ({N} commands)
    - {command_name}  ← step {N}, task {N}
```

### Documents Touched

```
DOCUMENTS TOUCHED:
  read:   {doc-name}, {doc-name}
  write:  {doc-name}
  update: {doc-name}
  delete: {doc-name}
```

### Variable Chain

```
VARIABLE CHAIN:
  {var} → {origin} → {consumers}
  {var} ← {origin} → {consumers, conditions}
```

### Dead Variables

Variables set in outputs but never consumed downstream.

```
DEAD VARIABLES:
  {var} ← {workflow-name} (outputs, never read)
```

---

## Task Type Badges

| Type | Badge |
|------|-------|
| document (search) | `[doc:search]` |
| document (save) | `[doc:save]` |
| document (update) | `[doc:update]` |
| document (bulk-save) | `[doc:bulk-save]` |
| document (bulk-update) | `[doc:bulk-update]` |
| document (delete) | `[doc:delete]` |
| connector | `[connector]` |
| prompt | `[prompt]` |
| mapping | `[mapping]` |

**Foreach annotation**: Append `(foreach, concurrent)` or `(foreach)` to the badge line.

**Connector detail line**: `connector: {name} > {command}`

---

## Execution Mode

When the user asks to trace a **real execution** (mentions times, durations, status, failures), switch to execution mode. See [api.md](./api.md) for MCP operation details.

### Trigger

- "Trace last execution of [agent]"
- "What failed in the last run of [agent]?"
- "Show execution times for [workflow]"

### E1. Select MCP Server

| Environment | MCP Server Prefix |
|-------------|-------------------|
| Local dev | `mcp__docker-localhost__` |

Additional environments depend on the project's MCP configuration. Pattern: `mcp__{project}-{env}__`.

### E2. Find Executions

```python
# Agent executions
{mcp}search_agent_executions(
    filters={"name": "{agent-name}"},
    sorters=["date", -1],
    page=1,
    page_size=5
)

# Workflow executions
{mcp}search_workflow_executions(
    filters={"name": "{workflow-name}"},
    sorters=["date", -1],
    page=1,
    page_size=5
)
```

Present recent executions with status, duration, tokens.

### E3. Get Full Execution

```python
# Agent execution (includes workflow list)
{mcp}get_agent_execution(
    agent_id="{execution_id}",
    compact=False
)

# Workflow execution (includes task list)
{mcp}get_workflow_execution(
    workflow_id="{workflow_run_id}",
    compact=False
)
```

### E4. Output Execution Trace

```
AGENT: {agent-name}  [RUN: {execution_id}]
  status: {status} | duration: {total_time}s | tokens: {total_tokens}
  started:  {date}
  finished: {finished_time}
  workflows: {completed}/{total}

  ┌─ STEP 1: {workflow-name}  [OK 3.2s]
  │  tasks:
  │    1. [doc:search]  load-config                      OK   0.4s
  │       inputs:  name: "config"
  │       outputs: competitions (3 items)
  │    2. [connector]   fetch-data                        OK   3.8s  ← slowest
  │       connector: my-connector > get_schedules
  │       inputs:  league_id: "sr:league:1"
  │       outputs: schedules (180 items)
  │
  ├─ STEP 2: {workflow-name}  [SKIP]
  │  reason: condition not met (has_live=False)
  │
  └─ STEP 3: {workflow-name}  [OK 0.9s]
     tasks:
       1. [doc:update]  unlock-season                    OK   0.9s
          inputs:  status: "unlocked"

EXECUTION SUMMARY:
  total:     4.1s
  tokens:    1,240
  workflows: 2/3 executed, 1 skipped
  slowest:   fetch-data (3.8s, step 1)
```

**Key annotations:**
1. **Timing per task**: `OK 0.4s` after each task name
2. **Slowest task**: `← slowest` annotation
3. **Skip reason**: condition that evaluated false with actual values
4. **Error details**: `FAIL` with inline error message
5. **Actual values**: Real input/output values from execution
6. **Foreach count**: `(foreach, 2 items)`
7. **Execution summary**: Totals, bottleneck, skip/fail counts

### E5. Failure Analysis

If any task has status `error`:

```
FAILURES:
  step 3, task 3: fetch-schedules
    status:  error
    time:    3.8s
    error:   "HTTPError 429: Rate limit exceeded"
    inputs:  league_id: "sr:league:1", season: "2025"
    impact:  blocks tasks 4-7 (parsed_fixtures never set)
    suggestion: Check API rate limits / add retry logic
```

### E6. Performance Insights (optional)

If user asks for performance analysis, fetch multiple executions and analyze patterns:

```
PERFORMANCE:
  avg execution:  18.2s (last 10 runs)
  p95 execution:  32.1s
  most common skip: steps 4-5 (72% of runs)
  most common fail: fetch-* (3%, rate limits)

TIMING BREAKDOWN:
  external API calls:  8.2s (58%)
  document operations:  4.8s (34%)
  connector (internal): 2.0s (14%)
```

---

## Mode Summary

| Mode | Trigger | Data Source | Shows |
|------|---------|-------------|-------|
| **Static** (default) | YAML path or entity name | Local YAML files | Structure, variables, conditions, inputs/outputs |
| **Execution** | Runtime keywords (times, failures) | MCP API | Times, status, failures, actual values |

## Tips

- Use **static mode** to understand design and variable flow before deploying
- Use **execution mode** to debug failures and find bottlenecks
- Start from **skill** to see all entry points, narrow to **agent** or **workflow**
- Use **document trace** to find all workflows that interact with a specific collection
- Use **input/output trace** to follow a variable across the entire chain
- Look for **dead variables** — outputs no downstream workflow consumes
- Check **conditions** — a workflow that never executes means empty outputs

## Related

- [Analyze](./analyze.md) — Full template component overview
- [Validate](./validate.md) — YAML structure validation
- [API](./api.md) — MCP operations for execution queries
