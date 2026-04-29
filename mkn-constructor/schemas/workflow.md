# Workflow YAML Schema

Workflows define task pipelines with sequential execution and state propagation between tasks.

**Location**: `agent-templates/<template-name>/workflows/<workflow-name>.yml`

---

## Root Structure

```yaml
workflow:
  name: <string>               # Required. Unique identifier (kebab-case)
  title: <string>               # Required. Human-readable title
  description: <string>         # Required. What this workflow does
  context-variables: <object>   # Optional. Connector credentials and settings
  inputs: <object>              # Optional. Parameters received from the agent
  outputs: <object>             # Optional. Values returned to the agent
  tasks: <list>                 # Required. Ordered list of tasks to execute
```

---

## Field Reference

### `name` (required)

Unique identifier. Must match the name referenced in the agent's `workflows` list.

```yaml
name: machina-assistant-reasoning
```

### `title` (required)

Human-readable display name.

```yaml
title: Machina Assistant - Reasoning
```

### `description` (required)

```yaml
description: Analyzes user questions to determine intent and search for relevant information
```

### `context-variables` (optional)

Connector credentials and configuration. Keys match connector names, values are credential mappings.

```yaml
context-variables:
  debugger:
    enabled: true
  google-genai:
    credential: $TEMP_CONTEXT_VARIABLE_VERTEX_AI_CREDENTIAL
    project_id: $TEMP_CONTEXT_VARIABLE_VERTEX_AI_PROJECT_ID
    api_key: $TEMP_CONTEXT_VARIABLE_GOOGLE_GENERATIVE_AI_API_KEY
  machina-ai:
    api_key: $TEMP_CONTEXT_VARIABLE_SDK_OPENAI_API_KEY
  machina-ai-fast:
    api_key: $TEMP_CONTEXT_VARIABLE_SDK_GROQ_API_KEY
  api-football:
    x-apisports-key: $TEMP_CONTEXT_VARIABLE_API_FOOTBALL_API_KEY
    api_key: $MACHINA_CONTEXT_VARIABLE_API_FOOTBALL_API_KEY
  openai:
    api_key: $TEMP_CONTEXT_VARIABLE_SDK_OPENAI_API_KEY
  google-storage:
    api_key: $TEMP_CONTEXT_VARIABLE_GOOGLE_STORAGE_API_KEY
    bucket_name: $TEMP_CONTEXT_VARIABLE_GOOGLE_STORAGE_BUCKET_NAME
```

**Credential prefixes**:
- `$TEMP_CONTEXT_VARIABLE_*` — testing/development credentials
- `$MACHINA_CONTEXT_VARIABLE_*` — production credentials

**`debugger`**: Special entry that enables workflow debug logging when `enabled: true`.

### `inputs` (optional)

Parameters received from the calling agent. Values are expressions evaluated against the agent's state.

```yaml
inputs:
  thread_id: $.get('thread_id')
  input_message: $.get('input_message')
  event_code: "$.get('event_code') or None"
  content_types: "$.get('content_types', ['meme', 'stats', 'quiz'])"
```

### `outputs` (optional)

Values returned to the calling agent after all tasks complete. Evaluated against the workflow's accumulated state.

```yaml
outputs:
  reasoning: $.get('reasoning', {})
  document_id: $.get('document_id', None)
  workflow-status: $.get('document_id') is not None and 'executed' or 'skipped'
```

**`workflow-status` pattern**: Nearly every workflow includes this field. The agent uses it to check if the workflow actually did work.

```yaml
# Boolean ternary — most common
workflow-status: $.get('document_id') is not None and 'executed' or 'skipped'

# Check a result field
workflow-status: $.get('message') is not None and 'executed' or 'skipped'

# Invert logic (skipped when condition is true)
workflow-status: "$.get('event_exists') is not True and 'skipped' or 'executed'"

# Static value set in last task
workflow-status: "$.get('workflow_executed_status', 'executed')"
```

**Computed outputs** — inline Python dicts:

```yaml
outputs:
  metadata: |
    {
      'team_a': $.get('team_a'),
      'team_b': $.get('team_b'),
      'generated_at': datetime.now().isoformat(),
      'version': '1.0.0'
    }
```

### `tasks` (required)

Ordered list of tasks. Each task reads from and writes to the shared workflow state via `$.get()`.

---

## Task Types

Every task shares these common fields:

```yaml
- type: <string>              # Required. "document", "prompt", "mapping", "connector"
  name: <string>              # Required. Unique within the workflow
  description: <string>       # Optional. What this task does
  condition: <expression>     # Optional. Skip if evaluates to False
  inputs: <object>            # Optional. Values passed to the task
  outputs: <object>           # Optional. Values extracted from the task response
  foreach: <object>           # Optional. Loop over a list
```

### Task Type: `prompt`

Calls an LLM via a connector to generate structured output.

```yaml
- type: prompt
  name: assistant-chat-reasoning-prompt
  condition: $.get('document_id') is not None
  connector:
    name: google-genai           # Connector name (must match context-variables)
    command: invoke_prompt        # Connector command
    model: gemini-2.5-flash      # Model identifier
    location: global             # Optional. Provider-specific
    provider: vertex_ai          # Optional. Provider-specific
  inputs:
    _1-conversation-history: $.get('messages_loaded', [])[-5:]
    _2-user-messages: $.get('input_message')
  outputs:
    reasoning: $                 # $ = entire LLM response (structured via schema)
```

**Input prefix convention**: Inputs prefixed with `_N-` (e.g., `_1-`, `_2-`) are ordered when passed to the prompt template. The prefix determines the order the variables appear in the prompt instruction.

**Connector fields**:

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Connector name from `context-variables` |
| `command` | Yes | `invoke_prompt`, `invoke_search`, `invoke_embedding`, `invoke_video` |
| `model` | No | Model identifier (e.g., `gemini-2.5-flash`, `gpt-4.1-mini`, `llama-3.3-70b-versatile`) |
| `location` | No | Region/location for provider (e.g., `global`) |
| `provider` | No | Backend provider (e.g., `vertex_ai`) |

**Output patterns**:

```yaml
# Entire structured response (when prompt has schema)
outputs:
  reasoning: $

# Extract specific field from response
outputs:
  search_queries: "$.get('search_queries', [])"

# Extract from OpenAI-style response
outputs:
  message: "$.get('choices')[0].get('message').get('content')"

# Build list from foreach iteration
outputs:
  search_response: |
    [
      $.get('answer', '')
    ]

# Build list of dicts from foreach
outputs:
  content_suggestions: |
    [
      {
        'content_type': $.get('content_type'),
        'caption': $.get('caption'),
        'hashtags': $.get('hashtags', [])
      }
    ]

# Bulk output for embedding snippets
outputs:
  research-standings-bulk: |
    [
      {
        'subject': '$.(title)',
        'text': c.get('content', ''),
        'title': f"$.(title) - {c.get('title', '')}",
        'metadata': {
          'event_code': '$.(event_code)',
          'language': 'en'
        }
      }
      for c in $.get('snippets', [])
    ]
```

### Task Type: `connector`

Calls an external service (Python script or REST API).

```yaml
- type: connector
  name: fetch-fixture
  connector:
    name: api-football
    command: get-fixtures
  inputs:
    id: "$.get('event_id')"
  outputs:
    fixture_data: "$.get('response', [{}])[0] if len($.get('response', [])) > 0 else {}"
    home_team_id: "$.get('response', [{}])[0].get('teams', {}).get('home', {}).get('id') if len($.get('response', [])) > 0 else None"
```

**Connector with foreach**:

```yaml
- type: connector
  name: search-google
  connector:
    name: google-genai
    command: invoke_search
    model: gemini-2.5-flash
  foreach:
    concurrent: true
    name: search_query
    expr: $
    value: ($.get('search_queries_team_b', []) + $.get('search_queries_team_a', []))
  inputs:
    search_query: $.get('search_query', '')
  outputs:
    search_response: |
      [
        $.get('answer', '')
      ]
```

**Literal string inputs** (must double-quote):

```yaml
inputs:
  provider: "'vertex_ai'"
  location: "'global'"
  model_name: "'veo-3.1-fast-generate-001'"
  poll_interval: "10"
```

### Task Type: `mapping`

Transforms data in-place using a named mapping definition. No external calls.

```yaml
- type: mapping
  name: api-football-mapping
  description: Transform the match data
  condition: "$.get('event_exists') is True"
  inputs:
    event_selected: "$.get('event_selected')"
  outputs:
    event_code: "$.get('event_code')"
    season: "$.get('season')"
    team_home_name: "$.get('team_home_name')"
    team_away_name: "$.get('team_away_name')"
```

Mapping tasks reference a named mapping from `mappings/*.yml`. The mapping's `outputs` expressions are evaluated, then the task's `outputs` extract from the result.

**Simple passthrough mapping** (used to prepare data):

```yaml
- type: mapping
  name: assistant-prepare-message-history
  condition: $.get('document_id') is not None
  inputs:
    message-history: $.get('messages')[-3:]
  outputs:
    message-history: $.get('message-history')
```

### Task Type: `document`

MongoDB operations. See [document.md](document.md) for complete reference.

```yaml
- type: document
  name: load-thread-document
  config:
    action: search
    search-limit: 1
    search-vector: false
  filters:
    name: "'thread'"
    document_id: $.get('thread_id')
  outputs:
    document_id: $.get('documents')[0].get('_id') if len($.get('documents', [])) > 0 else None
```

---

## `foreach` Reference

Loops a task over a list of items. Each iteration runs the task with the current item accessible via the named variable.

```yaml
foreach:
  name: <string>        # Variable name for current item
  expr: <expression>    # Expression context (usually $)
  value: <expression>   # List to iterate over
  concurrent: <bool>    # Optional. Run iterations in parallel
```

**Examples**:

```yaml
# Simple list iteration
foreach:
  name: query
  expr: $
  value: $.get('news_queries')

# Concatenated lists
foreach:
  name: search_query
  expr: $
  value: ($.get('search_queries_team_b', []) + $.get('search_queries_team_a', []))

# Iterate over content types
foreach:
  name: content_type
  expr: $
  value: $.get('content_types')

# Concurrent execution
foreach:
  concurrent: true
  name: search_query
  expr: $
  value: $.get('search_queries')
```

**Inside foreach**: Access the current item via `$.get('<foreach-name>')`. Access agent-level state via `context.get()`.

```yaml
inputs:
  search_query: $.get('search_query', '')  # Current item
  country: context.get('coverage-markets-country')  # Agent state
```

**Foreach outputs**: When a task with foreach produces outputs, list values are **accumulated** across iterations (appended, not replaced).

```yaml
outputs:
  search_response: |
    [
      $.get('answer', '')
    ]
# After 3 iterations: search_response = [answer1, answer2, answer3]
```

---

## `condition` Patterns

```yaml
# Null check
condition: $.get('document_id') is not None

# Boolean check
condition: $.get('event_exists') is True

# String equality
condition: "$.get('season_type') == 'PST'"

# Combined conditions
condition: "$.get('event_exists') is True and $.get('season') is not None"

# Length check
condition: "len($.get('search_queries', [])) > 0"

# Nested dict access
condition: $.get('chat_reasoning', {}).get('is_find_faq') is True

# Complex with or
condition: "($.get('search_queries_team_b') is not None and len($.get('search_queries_team_b', [])) > 0) or ($.get('search_queries_team_a') is not None and len($.get('search_queries_team_a', [])) > 0)"

# Negation
condition: "$.get('event_exists') is not True"

# Compound with parentheses
condition: ($.get('thread_id') is None or $.get('thread_id') == '') and ($.get('document_exists') is False or $.get('document_exists') is None)
```

---

## State Propagation

Each task's `outputs` are merged into the workflow's shared state. Subsequent tasks access accumulated state via `$.get()`.

```
Task 1 outputs: {document_id: "abc", document_value: {...}}
    ↓
Task 2 reads: $.get('document_id')  →  "abc"
Task 2 outputs: {reasoning: {...}}
    ↓
Task 3 reads: $.get('document_id')  →  "abc"  (still available)
Task 3 reads: $.get('reasoning')    →  {...}   (from Task 2)
    ↓
Workflow outputs: evaluated against final accumulated state
```

---

## Expression Syntax

```yaml
# Read from state
$.get('field')
$.get('field', 'default')
$.get('nested', {}).get('child')

# List operations
$.get('documents', [])[0].get('value', {})
len($.get('documents', []))
$.get('messages')[-3:]               # Last 3 items
$.get('messages')[-5:]               # Last 5 items

# Inline Python
datetime.now().isoformat()
datetime.utcnow()
timedelta(days=30)

# Spread operator in dicts
{**$.get('document_value'), 'status': 'updated'}

# Spread in lists
[*$.get('list_a', []), *$.get('list_b', [])]

# List comprehensions
[d.get('value', {}) for d in $.get('documents', [])]

# f-strings
f"{$.get('title')} - Standings Analysis"

# Ternary
$.get('documents')[0].get('_id') if len($.get('documents', [])) > 0 else None

# String concatenation
$.get('home_team_name') + ' vs ' + $.get('away_team_name')

# Type conversion
str($.get('event_id'))
int($.get('week_sequence', 1))

# Literal strings (double-quoted containing single quotes)
"'thread'"
"'REG'"
"'executed'"

# MongoDB query syntax (in filters/inputs)
"{'$in': ['sport:Event']}"
"{'$gt': datetime.utcnow() - timedelta(days=30)}"
"{'$ne': 'processed'}"

# Variable interpolation in outputs (special syntax)
'$.(title)'          # Resolves to workflow state value
'$.(event_code)'     # Used inside string contexts
```

---

## Naming Conventions

| Element | Convention | Example |
|---------|-----------|---------|
| Workflow name | `<template>-<action>` | `machina-assistant-reasoning` |
| Task name | `<verb>-<noun>` | `load-thread-document`, `fetch-fixture` |
| Prompt task name | matches prompt YAML name | `assistant-chat-reasoning-prompt` |
| Mapping task name | matches mapping YAML name | `api-football-mapping` |

---

## Common Mistakes

| Mistake | Correct |
|---------|---------|
| Missing `workflow:` root key | Must have `workflow:` as top-level key |
| `tasks:` outside `workflow:` | `tasks:` must be nested under `workflow:` |
| `${variable}` | `$.get('variable')` |
| Unquoted literal strings | `"'thread'"` not `thread` |
| `type: llm` | `type: prompt` |
| `type: api` | `type: connector` |
| Missing `context-variables` for connector | Connector credentials must be declared |
| `outputs: result` (no key) | `outputs:` must be key-value pairs |
| Forgetting `workflow-status` output | Always include for agent condition checks |
