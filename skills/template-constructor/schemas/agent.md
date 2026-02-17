# Agent YAML Schema

Complete reference for agent YAML files. Agents orchestrate workflows and define execution context.

**Location**: `agent-templates/<template-name>/agents/<agent-name>.yml`

---

## Root Structure

```yaml
agent:
  name: <string>           # Required. Unique identifier (kebab-case)
  title: <string>           # Required. Human-readable title
  description: <string>     # Required. What this agent does
  context: <object>         # Optional. Static agent configuration
  context-agent: <object>   # Optional. Dynamic input parameters from execution payload
  context-variables: <obj>  # Optional. Connector credentials and settings
  documents: <list>         # Optional. Embedded document definitions
  jobs: <list>              # Optional. Scheduled jobs (Celery Beat)
  workflows: <list>         # Required. Ordered list of workflows to execute
```

---

## Field Reference

### `name` (required)

Unique identifier for the agent. Must be kebab-case. Used to reference the agent in `_install.yml` and API calls.

```yaml
name: machina-assistant-executor
```

### `title` (required)

Human-readable display name.

```yaml
title: Machina Assistant - Chat Executor
```

### `description` (required)

Description of the agent's purpose. Can be a single line or multiline.

```yaml
# Single line
description: AI-powered assistant for platform questions

# Multiline
description: |
  An intelligent agent that generates engaging social media content
  for soccer teams using real-time statistics and news insights
```

### `context` (optional)

Static configuration values. Set once, available throughout execution.

```yaml
context:
  status: "inactive"              # Agent activation status
  config-frequency: 10            # Periodic execution interval (minutes)
```

**Known `context` fields**:

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | `"inactive"` or `"active"` — controls whether agent is enabled |
| `config-frequency` | integer | Execution interval in minutes for periodic/scheduled agents |

**Usage patterns**:

```yaml
# Chat agent (on-demand, starts inactive)
context:
  status: "inactive"

# Periodic agent (scheduled, no status needed)
context:
  config-frequency: 10

# Periodic agent that starts inactive
context:
  config-frequency: 10
  status: "inactive"

# One-time setup agent (run once, very high frequency = practically disabled)
context:
  config-frequency: 99999999
```

### `context-agent` (optional)

Dynamic input parameters extracted from the execution payload (`$.get()`). These are the parameters the caller passes when triggering the agent.

```yaml
# Chat agent — receives thread and messages
context-agent:
  thread_id: $.get('thread_id', None)
  messages: $.get('messages', [])

# One-shot agent — receives specific parameters
context-agent:
  team_a: $.get('team_a')
  team_b: $.get('team_b')
  language: $.get('language', 'en')

# Event-driven agent — receives event code
context-agent:
  event_code: "$.get('event_code')"

# Multi-parameter agent — receives user profile
context-agent:
  name: $.get('name')
  email_address: $.get('email_address')
  favorite_team: $.get('favorite_team')
  language: $.get('language')
```

### `context-variables` (optional)

Connector credentials and configuration. Usually defined at the workflow level, but can also appear at the agent level.

```yaml
context-variables:
  debugger:
    enabled: true
  google-genai:
    credential: $TEMP_CONTEXT_VARIABLE_VERTEX_AI_CREDENTIAL
    project_id: $TEMP_CONTEXT_VARIABLE_VERTEX_AI_PROJECT_ID
```

### `jobs` (optional)

Declarative scheduled jobs evaluated by Celery Beat. Each job dispatches a skill or agent at a defined interval or cron schedule.

```yaml
jobs:
  - name: <string>           # Required. Unique job identifier
    enabled: <boolean>       # Required. Toggle on/off
    type: <string>           # Required. "skill" or "agent"
    target: <string>         # Required. Skill or agent name to dispatch
    interval: <integer>      # Seconds between runs (mutually exclusive with cron)
    cron: <string>           # Cron expression (mutually exclusive with interval)
    context: <object>        # Optional. Passed as context-agent to target
```

**Fields**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Unique identifier for the job within the agent |
| `enabled` | boolean | Yes | `true` to activate, `false` to skip |
| `type` | string | Yes | `"skill"` dispatches via `skill_executor`, `"agent"` via `agent_executor` |
| `target` | string | Yes | Name of the skill or agent to invoke |
| `interval` | integer | No | Run every N seconds. Mutually exclusive with `cron` |
| `cron` | string | No | Cron expression (5-field). Mutually exclusive with `interval` |
| `context` | object | No | Key-value pairs passed as `context-agent` to the target |

**Scheduling**: Celery Beat ticks every 5 seconds. On each tick, agents with `status: "active"` and `jobs.enabled: True` are evaluated. Jobs fire when the interval/cron is due based on `last_execution`.

**Auto-managed fields** (set by scheduler at runtime, not in YAML):
- `last_execution` — timestamp of last dispatch
- `last_status` — `"dispatched"` after successful dispatch

**Examples**:

```yaml
# Interval-based: run every 30 seconds
jobs:
  - name: "quick-sync"
    enabled: true
    type: "skill"
    target: "my-sync-skill"
    interval: 30

# Cron-based: every Tuesday at 11:00
jobs:
  - name: "weekly-report"
    enabled: true
    type: "agent"
    target: "my-report-agent"
    cron: "0 11 * * 2"
    context:
      report_type: "weekly"
      language: "en"

# Multiple jobs on one agent
jobs:
  - name: "frequent-check"
    enabled: true
    type: "skill"
    target: "health-check-skill"
    interval: 10
  - name: "daily-cleanup"
    enabled: false
    type: "agent"
    target: "cleanup-agent"
    cron: "0 3 * * *"
```

**Cron expression reference** (5-field):

| Field | Values | Example |
|-------|--------|---------|
| Minute | 0-59 | `*/5` = every 5 min |
| Hour | 0-23 | `11` = 11:00 |
| Day of month | 1-31 | `1` = first day |
| Month | 1-12 | `*` = every month |
| Day of week | 0-6 (Sun=0) | `2` = Tuesday |

### `workflows` (required)

Ordered list of workflows to execute. Workflows run sequentially — each workflow can access outputs from previous workflows via `$.get()`.

```yaml
workflows:
  - name: <string>            # Required. Workflow name (must match a workflow YAML)
    description: <string>     # Required. What this workflow step does
    condition: <expression>   # Optional. Python expression — skip if False
    inputs: <object>          # Optional. Values passed to the workflow
    outputs: <object>         # Optional. Values extracted from workflow response
    foreach: <object>         # Optional. Loop execution over a list
```

---

## Workflow Entry Reference

### `name` (required)

Must match the `name` field of an installed workflow YAML.

```yaml
- name: machina-assistant-reasoning
```

**Note**: The same workflow name can appear multiple times in the list (e.g., calling the same sync workflow with different parameters).

### `description` (required)

Human-readable description for this workflow step.

```yaml
  description: Analyze user question and search for relevant information
```

### `condition` (optional)

Python expression evaluated at runtime. If it evaluates to `False`/`None`, the workflow step is skipped.

```yaml
# Simple null check
condition: $.get('document_id') is not None

# Boolean check
condition: $.get('event_exists') is True

# Combined conditions
condition: $.get('document_id') is not None and $.get('reasoning_status') is True

# Check nested dict value
condition: $.get('chat_reasoning', {}).get('is_find_faq') is True

# Check enum value
condition: $.get('instructions_reasoning', {}).get('action') == 'list'

# Check value in list
condition: $.get('instructions_reasoning', {}).get('action') in ['enable', 'disable']

# Check season type
condition: "$.get('season_type') == 'PST'"

# Multiple complex conditions
condition: $.get('event_exists') is True and $.get('output-documents') is not None

# Multiline condition (use pipe)
condition: |
  (
    $.get('document_id') is not None and
    $.get('instructions_reasoning', {}).get('action') == 'list'
  )
```

### `inputs` (optional)

Key-value pairs passed to the workflow. Values are Python expressions evaluated against the agent's current state.

```yaml
inputs:
  # Pass from context-agent
  thread_id: $.get('thread_id')
  input_message: $.get('messages', [])

  # Pass from previous workflow outputs
  document_id: $.get('document_id')
  reasoning: $.get('reasoning')

  # Pass literal string values (quoted within quotes)
  season_type: "'REG'"
  output_status: "'idle'"
  data_type: "'schedule.json'"

  # Pass computed values
  nfl_season_week: "str(int($.get('week_sequence', 1)) + 1)"
  season_year: "str($.get('season_year', 2025))"

  # Pass with defaults
  max_queries: "$.get('max_queries', 3)"
  language: "$.get('language', 'en')"
  content_types: $.get('content_types', ['meme', 'stats', 'quiz'])

  # Pass from context (agent-level state)
  country: context.get('coverage-markets-country')
```

### `outputs` (optional)

Key-value pairs extracted from the workflow response and merged into the agent's state. These become available to subsequent workflows via `$.get()`.

```yaml
outputs:
  # Extract simple values
  reasoning: $.get('reasoning')
  document_id: $.get('document_id')

  # Extract with defaults
  suggestions: $.get('suggestions', [])
  user_profile: $.get('user_profile')

  # Check workflow execution status
  workflow-status: $.get('workflow-status')
  reasoning_status: $.get('workflow-status') == 'executed'
  sync_status: "$.get('workflow-status', False)"

  # Extract nested values
  response_text: $.context.get('response_text', '')
  content: $.context.get('response_text', '')

  # Convert types
  week_sequence: "str($.get('week_sequence'))"

  # Return static values
  objects: []
  stream: true
```

### `foreach` (optional)

Loops the workflow execution over a list of items. Each iteration receives the current item.

```yaml
# Basic foreach
foreach:
  name: competitionItem     # Variable name for each item
  expr: $                   # Expression context (usually $)
  value: $.get('coverage-markets-mapping')  # List to iterate over
```

---

## Agent Type Patterns

### Chat Agent (Conversational)

On-demand agent triggered by user messages. Manages conversation threads.

```yaml
agent:
  name: my-chat-executor
  title: My Chat - Executor
  description: AI-powered chat assistant
  context:
    status: "inactive"
  context-agent:
    thread_id: $.get('thread_id', None)
    messages: $.get('messages', [])
  workflows:
    - name: my-chat-reasoning
      description: Analyze user message and determine intent
      condition: $.get('messages') is not None and len($.get('messages')) > 0
      inputs:
        thread_id: $.get('thread_id')
        input_message: $.get('messages', [])
      outputs:
        reasoning: $.get('reasoning')
        document_id: $.get('document_id')
        reasoning_status: $.get('workflow-status') == 'executed'

    - name: my-chat-response
      description: Generate response using LLM
      condition: $.get('document_id') is not None and $.get('reasoning_status') is True
      inputs:
        document_id: $.get('document_id')
        reasoning: $.get('reasoning')
      outputs:
        response_text: $.get('response_text')
        suggestions: $.get('suggestions', [])
        response_content: $.get('response_content')
        response_status: $.get('workflow-status') == 'executed'

    - name: my-chat-update
      description: Update conversation thread
      condition: $.get('document_id') is not None and $.get('response_status') is True
      inputs:
        document_id: $.get('document_id')
        response_content: $.get('response_content')
        response_text: $.get('response_text')
        suggestions: $.get('suggestions', [])
      outputs:
        thread_id: $.get('document_id')
        workflow-status: $.get('workflow-status')
        response_text: $.context.get('response_text', '')
        content: $.context.get('response_text', '')
        objects: []
        suggestions: $.context.get('suggestions', [])
```

**Key characteristics**:
- `context.status: "inactive"` — activated on-demand
- `context-agent` receives `thread_id` and `messages`
- Typical flow: reasoning → response → update
- Final outputs use `$.context.get()` to access agent state

### Scheduled Agent (Jobs)

Runs on a schedule via Celery Beat. Dispatches skills or agents at defined intervals or cron expressions.

```yaml
agent:
  name: my-data-scheduler
  title: My Data - Scheduler
  description: Periodically sync data from external APIs
  context:
    status: "active"
  jobs:
    # Interval: run every 30 seconds
    - name: "sync-data"
      enabled: true
      type: "skill"
      target: "my-sync-skill"
      interval: 30
      context:
        data_type: "latest"

    # Cron: run daily at 03:00
    - name: "daily-cleanup"
      enabled: true
      type: "agent"
      target: "my-cleanup-agent"
      cron: "0 3 * * *"
  workflows:
    - name: my-sync-data
      description: Sync latest data
      outputs:
        sync_status: "$.get('workflow-status', False)"

    - name: my-process-data
      description: Process synced data
      condition: "$.get('sync_status') == 'executed'"
      inputs:
        data_type: "'latest'"
      outputs:
        process_status: "$.get('workflow-status', False)"
```

**Key characteristics**:
- `status: "active"` required — scheduler only evaluates active agents
- `jobs` array defines scheduling rules (interval or cron)
- Each job targets a skill or agent by name
- `context` in the job is passed as `context-agent` to the target
- No `context-agent` on the agent itself (no user input)
- Often uses `foreach` for batch processing

> **Legacy**: `context.config-frequency: N` (APScheduler) is deprecated. Use `jobs` with `interval` or `cron` instead.

### One-Shot Agent (Single Request)

Processes a single request without thread management.

```yaml
agent:
  name: my-generator
  title: My Generator
  description: Generate content based on input parameters
  context-agent:
    team_a: $.get('team_a')
    team_b: $.get('team_b')
    language: $.get('language', 'en')
  workflows:
    - name: my-generate-content
      description: Generate content comparing inputs
      inputs:
        team_a: "$.get('team_a')"
        team_b: "$.get('team_b')"
        language: "$.get('language', 'en')"
      outputs:
        workflow-status: "$.get('workflow-status')"
        content: "$.get('content')"
        metadata: "$.get('metadata')"
```

**Key characteristics**:
- No `context` block (or no `status`/`config-frequency`)
- `context-agent` receives specific parameters
- Usually a single workflow or simple chain
- Returns results directly

### Pipeline Agent (Multi-Step Processing)

Chains multiple workflows sequentially, each building on previous results.

```yaml
agent:
  name: my-pipeline-agent
  title: My Pipeline Agent
  description: Multi-step content pipeline with generation, media, and delivery
  context-agent:
    document_id: "$.get('document_id')"
  workflows:
    - name: my-pipeline-generate
      description: Generate text content
      inputs:
        document_id: "$.get('document_id')"
      outputs:
        document_id: "$.get('document_id')"
        workflow-status: "$.get('workflow-status')"

    - name: my-pipeline-audio
      description: Generate audio from content
      condition: "$.get('document_id') is not None"
      inputs:
        document_id: "$.get('document_id')"
        voice_id: "$.get('voice_id')"
      outputs:
        document_id: "$.get('document_id')"
        workflow-status: "$.get('workflow-status')"
        audio_path: "$.get('audio_path')"

    - name: my-pipeline-image
      description: Generate cover image
      condition: "$.get('document_id') is not None"
      inputs:
        document_id: "$.get('document_id')"
      outputs:
        document_id: "$.get('document_id')"
        workflow-status: "$.get('workflow-status')"
        image_url: "$.get('image_url')"

    - name: my-pipeline-deliver
      description: Package and deliver final content
      condition: "$.get('document_id') is not None"
      inputs:
        document_id: "$.get('document_id')"
      outputs:
        workflow-status: "$.get('workflow-status')"
```

**Key characteristics**:
- Each workflow passes `document_id` forward
- All steps after the first have `condition: "$.get('document_id') is not None"`
- Each step enriches the same document

### Branching Agent (Conditional Routing)

Routes execution based on reasoning output. Different workflows run depending on conditions.

```yaml
agent:
  name: my-branching-executor
  title: My Branching - Executor
  description: Routes to different workflows based on intent analysis
  context:
    status: "inactive"
  context-agent:
    thread_id: $.get('thread_id', None)
    messages: $.get('messages', [])
  workflows:
    # Step 1: Analyze intent (always runs)
    - name: my-reasoning
      description: Analyze input and determine action
      inputs:
        input_message: $.get('messages', [])
        thread_id: $.get('thread_id')
      outputs:
        reasoning: $.get('reasoning')
        document_id: $.get('document_id')

    # Branch A: Search FAQ
    - name: my-search-faq
      description: Search FAQ knowledge base
      condition: $.get('document_id') is not None and $.get('reasoning', {}).get('is_faq') is True
      inputs:
        document_id: $.get('document_id')
      outputs:
        faq_results: $.get('faq_results')

    # Branch B: Search Events
    - name: my-search-events
      description: Search upcoming events
      condition: $.get('document_id') is not None and $.get('reasoning', {}).get('search_type') == 'events'
      inputs:
        document_id: $.get('document_id')
      outputs:
        event_results: $.get('event_results')

    # Branch C: Search Markets
    - name: my-search-markets
      description: Search market data
      condition: $.get('document_id') is not None and $.get('reasoning', {}).get('is_markets') is True
      inputs:
        document_id: $.get('document_id')
      outputs:
        market_results: $.get('market_results')

    # Final: Generate response (always runs if document exists)
    - name: my-response
      description: Generate final response
      condition: $.get('document_id') is not None
      inputs:
        document_id: $.get('document_id')
        faq_results: $.get('faq_results')
        event_results: $.get('event_results')
        market_results: $.get('market_results')
      outputs:
        response_text: $.get('response_text')
```

**Key characteristics**:
- First workflow (reasoning) always runs
- Middle workflows have mutually exclusive or independent conditions
- Final workflow collects all results regardless of which branches ran
- Non-executed branches pass `None` forward (handled by defaults)

### Foreach Agent (Batch Processing)

Iterates over a list of items, running a workflow for each.

```yaml
agent:
  name: my-batch-processor
  title: My Batch Processor
  description: Process multiple items in batch with foreach
  context:
    config-frequency: 10
  workflows:
    # Step 1: Load configuration
    - name: my-load-config
      description: Load processing configuration
      outputs:
        item_list: $.get('item_list')
        processing_params: $.get('processing_params')

    # Step 2: Process each item
    - name: my-process-item
      description: Process individual items
      foreach:
        name: currentItem
        expr: $
        value: $.get('item_list')
      inputs:
        param: context.get('processing_params')
```

**Key characteristics**:
- `foreach.name` — variable name for current item in the loop
- `foreach.expr` — expression context (typically `$`)
- `foreach.value` — the list to iterate over
- Use `context.get()` inside foreach to access agent-level state

---

## Expression Syntax

All expressions use Python syntax with `$.get()` for state access.

```yaml
# Access current state
$.get('field_name')
$.get('field_name', 'default_value')

# Access nested values
$.get('reasoning', {}).get('action')

# Access agent context (in final workflow outputs)
$.context.get('response_text', '')

# Access agent context (inside foreach inputs)
context.get('coverage-markets-country')

# Type conversion
str($.get('week_sequence'))
int($.get('week_sequence', 1))

# String operations
"str($.get('season_year', 2025))"

# Computed values
"str(int($.get('week_sequence', 1)) + 1)"

# Ternary/conditional expressions
"str($.get('pst_week')) if $.get('season_type') == 'PST' else str($.get('week_sequence', 1))"

# List operations
len($.get('documents', []))
$.get('documents')[0].get('value', {})

# Boolean comparisons
$.get('workflow-status') == 'executed'
$.get('workflow-status', 'skipped') == 'executed'

# Literal string values (must double-quote)
"'REG'"
"'idle'"
"'schedule.json'"
```

---

## Naming Conventions

| Element | Convention | Example |
|---------|-----------|---------|
| Agent name | `<template>-<role>` | `machina-assistant-executor` |
| Workflow name | `<template>-<action>` | `machina-assistant-reasoning` |
| Chat agents | `*-executor` suffix | `support-assistant-chat-executor` |
| Schedulers | `*-scheduler` suffix | `statistics-scheduler` |
| Consumers | `*-consumer` suffix | `coverage-event-narration-consumer` |

---

## Common Mistakes

| Mistake | Correct |
|---------|---------|
| `workflow:` (singular root) | `agent:` is the root key |
| `type: agent` | No `type` field — root key `agent:` is sufficient |
| `${variable}` | `$.get('variable')` |
| `$variable` | `$.get('variable')` |
| Missing quotes on literal strings | `"'REG'"` not `REG` |
| `condition: true` | `condition: $.get('field') is True` |
| Using `context-agent` on periodic agents | Periodic agents have no caller — use `context` instead |
