# Machina Template YAML Reference

**Version**: 1.1
**Last Updated**: 2026-01-18
**Source**: Extracted from real codebase examples

This guide documents the **actual** YAML structures used in Machina templates, based on working examples from `dazn-templates` and `entain-templates`.

## Table of Contents

1. [Agent YAML](#agent-yaml)
   - [Periodic Agents](#periodic-agents)
   - [Streaming Status Messages](#streaming-status-messages)
2. [Workflow YAML](#workflow-yaml)
3. [Task Types](#task-types)
   - [Document Task](#document-task)
   - [Vector Search](#vector-search)
   - [Prompt Task](#prompt-task)
   - [Mapping Task](#mapping-task)
   - [Connector Task](#connector-task)
   - [Foreach Loops](#foreach-loops)
4. [Prompt YAML](#prompt-yaml)
5. [Mapping YAML](#mapping-yaml)
6. [Connector YAML](#connector-yaml)
7. [Installation Manifest](#installation-manifest)
8. [Expression Syntax](#expression-syntax)

---

## Agent YAML

Agents orchestrate workflows and manage conversation state.

### Structure

```yaml
agent:
  name: agent-name                    # Unique identifier (kebab-case)
  title: Agent Title                  # Human-readable title
  description: What this agent does   # Brief description

  # Agent behavior configuration
  context:
    status: "inactive"                # "active" or "inactive"
    config-frequency: 60              # (optional) Periodic execution interval in minutes

  # Input parameters from execution context
  context-agent:
    param_name: $.get('param_name', default_value)
    messages: $.get('messages', [])
    thread_id: $.get('thread_id', None)

  # Workflows to execute (in order)
  workflows:
    - name: workflow-name
      description: What this workflow does
      condition: $.get('some_value') is not None    # (optional) Skip if false
      inputs:
        input_param: $.get('context_value')
      outputs:
        output_param: $.get('workflow_output')
```

### Real Example

From `dazn-templates/agent-templates/moderator-assistant/agents/chat-executor.yml`:

```yaml
agent:
  name: moderator-chat-executor
  title: Moderator - Chat Executor
  description: Moderator Executor Agent.
  context:
    status: "inactive"
  context-agent:
    event_document_id: $.get('event_document_id', None)
    messages: $.get('messages', [])
    thread_id: $.get('thread_id', None)
    username: $.get('username', 'Anonimo')
  workflows:
    - name: moderator-chat-reasoning
      description: Assistant Chat Reasoning
      inputs:
        event_document_id: $.get('event_document_id', None)
        input_message: $.get('messages', [])
        thread_id: $.get('thread_id')
      outputs:
        chat_reasoning: $.get('chat_reasoning')
        document_id: $.get('document_id')

    - name: moderator-chat-response
      description: Moderator Chat Response
      condition: $.get('document_id') is not None
      inputs:
        chat_reasoning: $.get('chat_reasoning')
        document_id: $.get('document_id')
      outputs:
        document_content: $.get('document_content')
```

### Key Points

- **Workflows execute sequentially** - outputs from earlier workflows are available to later ones
- **Conditions use Python expressions** - `$.get('var') is not None`, `len($.get('list', [])) > 0`
- **context-agent receives execution params** - passed via `mcp__*__execute_agent(context={"context-agent": {...}})`

### Periodic Agents

Agents can be scheduled to run automatically at fixed intervals using `config-frequency`.

```yaml
agent:
  name: power-ranking-periodic
  title: Power Ranking - Periodic Agent
  description: Generates weekly power rankings automatically
  context:
    status: "active"              # Must be "active" for scheduler
    config-frequency: 60          # Run every 60 minutes
  context-agent:
    # No external params needed - agent is self-contained
  workflows:
    - name: check-and-generate-rankings
      description: Check if Monday and generate rankings
```

**Configuration Options:**

| Option | Type | Description |
|--------|------|-------------|
| `config-frequency` | integer | Execution interval in minutes |
| `status` | string | Must be `"active"` for scheduler to pick up |

**Best Practices:**

1. **Idempotency** - Periodic agents should check if work was already done
2. **Guard conditions** - Use workflow conditions to skip unnecessary runs
3. **Execution tracking** - Save execution documents to prevent duplicates

```yaml
# Example: Monday-only execution with idempotency
workflows:
  - name: check-monday-guard
    description: Only run on Mondays
    condition: |
      datetime.now().weekday() == 0  # Monday = 0
    outputs:
      is_monday: True

  - name: check-already-executed
    condition: $.get('is_monday') == True
    # Search for existing execution document for today
    # Skip if already exists
```

### Streaming Status Messages

Send real-time status updates to the client during agent execution using `stream_status_message`.

```yaml
# In agent workflow outputs:
workflows:
  - name: find-events-workflow
    outputs:
      step_find_events_objects: $.get('events', [])
      stream_status_message: |
        (
          '🔍 Searching events... found ' + str(len($.get('events', []))) + ' match' +
          ('es' if len($.get('events', [])) != 1 else '')
        ) if len($.get('events', [])) > 0 else '🔍 Searching events...'
```

**How it works:**

1. Each workflow can output a `stream_status_message`
2. Messages are sent to the client in real-time via SSE/WebSocket
3. Useful for long-running operations to show progress

**Common Patterns:**

```yaml
# Simple loading message
stream_status_message: "'🔄 Processing...'"

# Dynamic count message
stream_status_message: |
  f"📊 Found {len($.get('results', []))} results"

# Conditional message
stream_status_message: |
  '✅ Complete' if $.get('success') else '⏳ Working...'

# Multi-step progress
stream_status_message: |
  (
    '1/3 🔍 Searching...' if $.get('step') == 1 else
    '2/3 📝 Processing...' if $.get('step') == 2 else
    '3/3 ✅ Finishing...'
  )
```

---

## Workflow YAML

Workflows define a sequence of tasks that process data.

### Structure

```yaml
workflow:
  name: workflow-name                 # Unique identifier (kebab-case)
  title: Workflow Title               # Human-readable title
  description: What this workflow does

  # Credentials and API keys
  context-variables:
    debugger:
      enabled: true                   # Enable debug logging (captures task details)
    google-genai:
      credential: $TEMP_CONTEXT_VARIABLE_VERTEX_AI_CREDENTIAL
      project_id: $TEMP_CONTEXT_VARIABLE_VERTEX_AI_PROJECT_ID
    machina-ai:
      api_key: $TEMP_CONTEXT_VARIABLE_SDK_OPENAI_API_KEY

  # Input parameters
  inputs:
    param_name: $.get('param_name')
    optional_param: $.get('optional_param', 'default')

  # Output values (workflow-status is REQUIRED)
  outputs:
    result: $.get('computed_result')
    workflow-status: $.get('success') is True and 'executed' or 'skipped'  # REQUIRED!

  # Task sequence
  tasks:
    - type: document|prompt|mapping|connector
      name: task-name
      # ... task-specific fields
```

**Required Fields:**

| Field | Description |
|-------|-------------|
| `name` | Alphanumeric + hyphens only |
| `title` | Human-readable title |
| `outputs` | Must include `workflow-status` key |
| `tasks` | Non-empty list of tasks |

**⚠️ Important:** Every workflow **must** have `workflow-status` in outputs. This is validated by the SDK.

### Debugger Mode

Enable detailed task logging by setting `debugger.enabled: true` in context-variables:

```yaml
context-variables:
  debugger:
    enabled: true
```

When enabled, the SDK captures:
- Full task context (inputs, filters, config)
- Output responses from each task
- Execution timing and token usage
- Sensitive fields are filtered (api_key, secret, token, password)

### Real Example

From `dazn-templates/agent-templates/moderator-assistant/workflows/chat-reasoning.yml`:

```yaml
workflow:
  name: moderator-chat-reasoning
  title: Moderator - Chat Reasoning
  description: Workflow to execute a reasoning for a Moderator chat.
  context-variables:
    debugger:
      enabled: true
    google-genai:
      credential: $TEMP_CONTEXT_VARIABLE_VERTEX_AI_CREDENTIAL
      project_id: $TEMP_CONTEXT_VARIABLE_VERTEX_AI_PROJECT_ID
  inputs:
    event_document_id: $.get('event_document_id')
    input_message: $.get('input_message')
    thread_id: $.get('thread_id')
  outputs:
    chat_reasoning: $.get('chat_reasoning', {})
    document_id: $.get('document_id', None)
    workflow-status: $.get('document_exists') is True and 'executed' or 'skipped'
  tasks:
    # ... tasks defined below
```

---

## Task Types

### Document Task

Read, create, update, or search documents in MongoDB.

```yaml
- type: document
  name: task-name
  description: What this task does
  condition: $.get('document_id') is not None    # (optional)
  config:
    action: search|save|update|bulk-save|bulk-update
    search-limit: 10                              # For search actions
    search-vector: false                          # Enable vector search
    search-sorters: [["updated", -1]]             # Sort results (field, direction)
    embed-vector: false                           # For save/update - create embeddings
    embed-selector: "value.content"               # Field path for embedding text
    force-update: true                            # For update - force even if unchanged
  filters:                                        # MongoDB filters
    name: "'document-name'"                       # Note: strings need quotes inside
    document_id: $.get('document_id')
  inputs:                                         # Additional filter inputs
    name: "{'$in': ['type1', 'type2']}"
  documents:                                      # For save/update actions
    document_name: |
      {
        'field': $.get('value'),
        'nested': {
          'key': 'value'
        }
      }
  outputs:
    documents: $.get('documents', [])
    document_exists: len($.get('documents', [])) > 0
    first_doc: $.get('documents')[0] if len($.get('documents', [])) > 0 else {}
```

**Configuration Options:**

| Option | Type | Description |
|--------|------|-------------|
| `action` | string | Operation: search, save, update, bulk-save, bulk-update |
| `search-limit` | integer | Maximum documents to return (default: 10) |
| `search-sorters` | array | Sort config `[["field", -1]]` (-1=desc, 1=asc) |
| `search-vector` | boolean | Enable vector similarity search |
| `embed-vector` | boolean | Generate embedding when saving/updating |
| `embed-selector` | string | Field path for embedding (e.g., "value.content") |
| `force-update` | boolean | Force update even if document unchanged |

**Actions:**
- `search` - Query documents with filters
- `save` - Create new document(s)
- `update` - Update existing document(s)
- `bulk-save` - Create multiple documents at once
- `bulk-update` - Update multiple documents at once

### Vector Search

Enable semantic similarity search using embeddings.

**Configuration Options:**

| Option | Type | Description |
|--------|------|-------------|
| `search-vector` | boolean | Enable vector similarity search |
| `embed-vector` | boolean | Generate embedding when saving/updating |
| `threshold-docs` | integer | Minimum documents to return (default: 5) |
| `threshold-similarity` | float | Minimum similarity score 0.0-1.0 (default: 0.01) |
| `search-limit` | integer | Maximum documents to search (default: 1000) |

**Basic Vector Search:**

```yaml
- type: document
  name: find-similar-content
  config:
    action: search
    search-vector: true
    threshold-docs: 5
    threshold-similarity: 0.01
    search-limit: 1000
  connector:
    name: machina-ai
    command: invoke_embedding
    model: text-embedding-3-small
  inputs:
    name: "'content-snippet'"
    search-query: $.get('user_question')
  outputs:
    similar_docs: |
      [
        {
          **d.get('value', {}),
          'similarity': d.get('similarity_score', 0)
        }
        for d in $.get('documents', [])
      ]
```

**Save with Embedding:**

```yaml
- type: document
  name: save-with-embedding
  config:
    action: save
    embed-vector: true              # Generate embedding on save
  connector:
    name: machina-ai
    command: invoke_embedding
    model: text-embedding-3-small
  documents:
    content-snippet: |
      {
        'title': $.get('title'),
        'content': $.get('content'),
        'category': $.get('category')
      }
  metadata:
    category: $.get('category')
```

**Combined Filter + Vector Search:**

```yaml
- type: document
  name: search-league-content
  config:
    action: search
    search-vector: true
    search-limit: 100
  connector:
    name: machina-ai
    command: invoke_embedding
    model: text-embedding-3-small
  filters:
    name: "'content-snippet'"
  inputs:
    metadata.league: "'Premier League'"    # Filter first, then vector search
    search-query: $.get('user_question')
  outputs:
    results: $.get('documents', [])
```

**Standard Search (No Vector):**

```yaml
- type: document
  name: list-documents
  config:
    action: search
    search-vector: false          # Explicit: filter-only search
    search-limit: 50
  filters:
    name: "'thread'"
    document_id: $.get('thread_id')
  outputs:
    thread: $.get('documents')[0] if len($.get('documents', [])) > 0 else {}
```

**RAG Pattern (Retrieval-Augmented Generation):**

```yaml
tasks:
  # 1. Vector search for context
  - type: document
    name: find-context
    config:
      action: search
      search-vector: true
      threshold-docs: 5
    connector:
      name: machina-ai
      command: invoke_embedding
      model: text-embedding-3-small
    inputs:
      name: "'knowledge-base'"
      search-query: $.get('user_question')
    outputs:
      context_docs: $.get('documents', [])

  # 2. Generate answer with retrieved context
  - type: prompt
    name: generate-answer
    connector:
      name: machina-ai
      command: invoke_prompt
      model: gpt-4o
    inputs:
      _0-context: $.get('context_docs')
      _1-question: $.get('user_question')
    outputs:
      answer: $.get('response')
```

### Prompt Task

Execute an LLM prompt via a connector.

```yaml
- type: prompt
  name: prompt-name                              # References a prompt definition
  description: What this prompt does
  condition: $.get('document_id') is not None
  connector:
    name: google-genai                           # Connector to use
    command: invoke_prompt                       # Command to execute
    model: gemini-3-flash-preview                # Model name
    stream: true                                 # (optional) Enable streaming
    temperature: 0.7                             # (optional) LLM temperature
    location: global                             # (optional) Region
    provider: vertex_ai                          # (optional) Provider
  tools:                                         # (optional) LLM tools/functions
    - name: search_documents
      description: Search for relevant documents
      parameters:
        type: object
        properties:
          query:
            type: string
  foreach:                                       # (optional) Loop over items
    concurrent: true                             # Run in parallel
    name: item                                   # Variable name for current item
    expr: $                                      # Expression for item value
    value: $.get('items_list', [])               # List to iterate
  inputs:
    _0-first-input: $.get('some_value')          # Inputs are ordered by prefix
    _1-second-input: $.get('other_value')
  outputs:
    result: $                                    # $ = full response
    specific_field: $.get('field_name')          # Extract specific field
```

**Connector Options:**

| Option | Type | Description |
|--------|------|-------------|
| `name` | string | Connector name (required) |
| `command` | string | Command to execute (required) |
| `model` | string | Model identifier (required) |
| `stream` | boolean | Enable streaming output |
| `temperature` | float | LLM temperature (default: 0) |
| `location` | string | Deployment region |
| `provider` | string | LLM provider |
| `project_id` | string | Project identifier |

**Tools (Function Calling):**

```yaml
- type: prompt
  name: prompt-with-tools
  connector:
    name: machina-ai
    command: invoke_prompt
    model: gpt-4o
  tools:
    - name: get_weather
      description: Get current weather for a location
      parameters:
        type: object
        required: [location]
        properties:
          location:
            type: string
            description: City name
  inputs:
    _0-question: $.get('user_question')
  outputs:
    response: $.get('response')
    tool_calls: $.get('tool_calls', [])
```

### Mapping Task

Execute a data transformation mapping.

```yaml
- type: mapping
  name: mapping-name                             # References a mapping definition
  condition: $.get('document_id') is not None
  inputs:
    input_data: $.get('raw_data')
  outputs:
    transformed_data: $.get('transformed_data')
```

### Connector Task

Execute a custom connector command.

```yaml
- type: connector
  name: task-name
  description: What this task does
  condition: $.get('data') is not None
  connector:
    name: connector-name                         # Connector to use
    command: command_name                        # Command to execute
  inputs:
    param1: $.get('value1')
    param2: $.get('value2')
  outputs:
    result: $.get('result')                      # Access data fields directly
```

**Connector Return & Output Abstraction:**

Connectors return `{"status": bool, "data": {...}, "message": str}`. The SDK **automatically unwraps** the `data` object:

```python
# Connector returns:
return {
    "status": True,
    "data": {"file_path": "/tmp/out.mp4", "size": 1024},
    "message": "Done"
}
```

```yaml
# Workflow accesses directly (no "data." prefix):
outputs:
  file_path: $.get('file_path')    # ✅ Correct
  size: $.get('size')              # ✅ Correct
  # file_path: $.get('data').get('file_path')  # ❌ Wrong - don't do this
```

### Foreach Loops

Execute a task multiple times over a list of items. Works with all task types.

**Structure:**

```yaml
- type: prompt|document|connector|mapping
  name: task-name
  foreach:
    name: item_var           # Variable name for current item
    expr: $                  # Expression to access item (usually $)
    value: $.get('items')    # List to iterate over
    concurrent: true         # (optional) Run iterations in parallel
  inputs:
    current_item: $.get('item_var')      # Access current item
    item_field: $.get('item_var').get('field')
  outputs:
    results: $               # Collects all iteration results
```

**Configuration Options:**

| Option | Type | Description |
|--------|------|-------------|
| `name` | string | Variable name to access current item |
| `expr` | string | Expression for item value (usually `$`) |
| `value` | expression | List expression to iterate over |
| `concurrent` | boolean | Run iterations in parallel (default: false) |
| `limit` | integer | Maximum items to iterate (optional) |

**Error Handling:**

```yaml
- type: connector
  name: fetch-with-retry
  foreach:
    name: item
    value: $.get('items')
    concurrent: true
  continue_on_error: true    # Don't fail workflow if some iterations fail
  connector:
    name: external-api
    command: fetch
```

When `continue_on_error: true`, failed iterations are skipped and the workflow continues with successful results.

**Example: Process Multiple Events**

```yaml
- type: connector
  name: fetch-event-details
  foreach:
    name: event_code
    expr: $
    value: $.get('event_codes')    # ['sr:match:1', 'sr:match:2', ...]
    concurrent: true               # Fetch all in parallel
  connector:
    name: sportradar
    command: get_event
  inputs:
    event_id: $.get('event_code')
  outputs:
    event_details: |
      [
        {
          'code': item.get('event_code'),
          'data': item.get('response')
        }
        for item in $
      ]
```

**Example: Generate Content for Each Item**

```yaml
- type: prompt
  name: generate-summaries
  foreach:
    name: article
    expr: $
    value: $.get('articles')
    concurrent: true
  connector:
    name: machina-ai
    command: invoke_prompt
    model: gpt-4o
  inputs:
    _0-content: $.get('article').get('content')
  outputs:
    summaries: |
      [item.get('summary') for item in $]
```

**Example: Save Multiple Documents**

```yaml
- type: document
  name: save-processed-items
  foreach:
    name: item
    expr: $
    value: $.get('processed_items')
  config:
    action: save
    embed-vector: false
  documents:
    processed-item: |
      {
        'title': $.get('item').get('title'),
        'data': $.get('item').get('data'),
        'processed_at': datetime.now().isoformat()
      }
  metadata:
    item_id: $.get('item').get('id')
```

**Output Handling:**

When using `foreach`, the task output `$` contains a list of all iteration results:

```yaml
outputs:
  # Collect all results as-is
  all_results: $

  # Extract specific field from each result
  all_summaries: "[item.get('summary') for item in $]"

  # Filter successful results
  successful: "[item for item in $ if item.get('status')]"

  # Flatten nested lists
  all_items: "[x for item in $ for x in item.get('items', [])]"
```

---

## Prompt YAML

Prompts define LLM instructions with structured output schemas.

### Structure

```yaml
prompts:
  - type: prompt
    name: prompt-name
    title: Prompt Title
    description: What this prompt does
    instruction: |
      You receive these inputs:
      - _0-input-name: Description of input

      Your task is to...

      Rules:
      1. First rule
      2. Second rule
    schema:
      title: SchemaName
      description: What the output represents
      type: object
      required: [field1, field2]
      properties:
        field1:
          type: string
          description: Description of field1
        field2:
          type: boolean
          description: Description of field2
        field3:
          type: array
          items:
            type: string
```

### Real Example

From `dazn-templates/agent-templates/moderator-assistant/prompts/chat-reasoning.yml`:

```yaml
prompts:
  - type: prompt
    name: moderator-chat-reasoning-analyzer
    title: Moderator - Chat Reasoning Analyzer
    description: Analyzes user messages to determine intent
    instruction: |
      You receive 4 inputs:
      - _0-event-title: Event name (empty string "" if no event loaded)
      - _1-message-history: Previous messages
      - _2-user-question: Current question
      - _3-is-count-query: Boolean

      STEP 1 - CHECK IF EVENT IS LOADED:
      Look at _0-event-title input:
      - If empty → No event loaded
      - If has text → Event IS loaded

      STEP 2 - SET FLAGS:
      - is_find_event: True if user asks to find events
      - is_create_poll: True if user wants to create poll
    schema:
      title: ModeratorChatReasoningAnalyzer
      type: object
      required: [is_find_event, is_create_poll, short_message]
      properties:
        is_find_event:
          type: boolean
          description: User wants to find/search events
        is_create_poll:
          type: boolean
          description: User wants to create a poll
        short_message:
          type: string
          description: Loading status message (max 60 chars)
```

---

## Mapping YAML

Mappings define data transformations using Python expressions.

### Structure

```yaml
mappings:
  - type: mapping
    name: mapping-name
    title: Mapping Title
    description: What this mapping does
    outputs:
      output_field: |
        # Python expression
        $.get('input_field', 'default')

      computed_field: |
        # Complex expression
        len($.get('items', [])) > 0 and $.get('items')[0] or None

      formatted_text: |
        # String formatting
        f"Found {len($.get('results', []))} results"
```

### Real Example

From `dazn-templates/agent-templates/moderator-assistant/mappings/chat-documents.yml`:

```yaml
mappings:
  - type: mapping
    name: detect-count-queries
    title: Moderator - Detect Count Queries
    description: Deterministic keyword detection for count queries
    outputs:
      detected_count_query: |
        (
          str($.get('last_message', '')).strip().lower().startswith('quantas') or
          str($.get('last_message', '')).strip().lower().startswith('how many') or
          str($.get('last_message', '')).strip().lower().startswith('count')
        )
```

---

## Connector YAML

Connectors integrate with external APIs or run custom Python code.

### PyScript Connector

```yaml
connector:
  name: connector-name
  description: What this connector does
  filename: connector-name.py           # Python file name
  filetype: pyscript                    # "pyscript" for Python
  commands:
    - name: Human Readable Name
      value: function_name              # Python function to call
    - name: Another Command
      value: another_function
```

### REST API Connector

```yaml
connector:
  name: connector-name
  description: API description
  filename: connector-name.json         # OpenAPI spec file
  filetype: restapi                     # "restapi" for REST APIs
```

### Real Example

From `machina-templates/connectors/google-genai/google-genai.yml`:

```yaml
connector:
  name: google-genai
  description: This connector is the google-genai
  filename: google-genai.py
  filetype: pyscript
  commands:
    - name: Prompt
      value: invoke_prompt
    - name: Image
      value: invoke_image
    - name: Web Search
      value: invoke_search
    - name: Video
      value: invoke_video
```

---

## Installation Manifest

The `_install.yml` file defines how to install a template.

### Structure

```yaml
setup:
  title: Template Name
  description: What this template does
  category:
    - category-name                     # e.g., special-templates, connectors
  estimatedTime: 15 minutes
  features:
    - Feature description 1
    - Feature description 2
  integrations:
    - machina-ai                        # Required connectors
    - google-genai
  status: available
  value: agent-templates/template-name  # Template path
  version: 1.0.0

datasets:
  # Install order matters - dependencies first

  # Connectors
  - type: connector
    path: scripts/custom-connector.yml

  # Prompts
  - type: prompts
    path: prompts/reasoning.yml

  # Mappings
  - type: mappings
    path: mappings/transformations.yml

  # Workflows
  - type: workflow
    path: workflows/main-workflow.yml

  # Agents
  - type: agent
    path: agents/chat-executor.yml
```

### Dataset Types

| Type | Description |
|------|-------------|
| `agent` | Agent definition file |
| `workflow` | Workflow definition file |
| `prompts` | Prompt definitions file (can contain multiple) |
| `mappings` | Mapping definitions file (can contain multiple) |
| `connector` | Connector definition file |
| `document` | Document/config file to create |

---

## Expression Syntax

All expressions use Python syntax with a special `$` context object.

### Basic Access

```yaml
# Get value with default
value: $.get('field_name', 'default')

# Get nested value
nested: $.get('parent', {}).get('child', 'default')

# Access context
timestamp: context.get('current_timestamp')
```

### Conditional Expressions

```yaml
# Ternary
status: $.get('success') is True and 'executed' or 'skipped'

# None check
condition: $.get('document_id') is not None

# Boolean check
condition: $.get('chat_reasoning', {}).get('is_create_poll') == True
```

### List Operations

```yaml
# Length check
condition: len($.get('items', [])) > 0

# First item
first: $.get('items')[0] if len($.get('items', [])) > 0 else None

# Slice
recent: $.get('messages')[-3:]

# List comprehension
filtered: "[item for item in $.get('items', []) if item.get('active')]"

# Spread operator
combined: |
  [
    *$.get('list1', []),
    *$.get('list2', [])
  ]
```

### String Operations

```yaml
# F-string
message: f"Found {len($.get('results', []))} items"

# Multiline with join
summary: |
  '\n'.join([
    line for line in [
      f"Item 1: {$.get('val1')}",
      f"Item 2: {$.get('val2')}"
    ] if line
  ])
```

### Object Construction

```yaml
# Build object
new_doc: |
  {
    'field1': $.get('value1'),
    'field2': $.get('value2'),
    'nested': {
      'key': 'value'
    }
  }

# Merge objects
merged: |
  {
    **$.get('base_object', {}),
    'new_field': $.get('new_value')
  }
```

---

## Common Patterns

### One-Shot Agent (No Thread Required)

Create thread automatically if not provided:

```yaml
# In workflow tasks:
- type: document
  name: create-new-thread
  condition: $.get('thread_id') is None
  config:
    action: save
    embed-vector: false
  documents:
    thread: |
      {
        'agent_id': 'agent-name',
        'messages': [],
        'status': 'active',
        'source': 'one-shot'
      }
  outputs:
    thread_id: $.get('documents')[0].get('_id')
```

### Streaming Status Updates

Send status messages during execution:

```yaml
# In agent workflow outputs:
outputs:
  stream_status_message: |
    '🔍 Searching...' if $.get('searching') else '✅ Complete'
```

### Conditional Workflow Execution

```yaml
# In agent workflows:
- name: create-poll-workflow
  condition: |
    (
      $.get('document_id') is not None and
      $.get('reasoning', {}).get('should_create_poll') == True
    )
```

---

## File Organization

```
agent-templates/template-name/
├── _install.yml              # Installation manifest
├── agents/
│   └── chat-executor.yml     # Agent definitions
├── workflows/
│   ├── main-workflow.yml     # Main workflow
│   └── helper-workflow.yml   # Supporting workflows
├── prompts/
│   └── reasoning.yml         # Prompt definitions
├── mappings/
│   └── transformations.yml   # Mapping definitions
├── scripts/
│   ├── connector.yml         # Connector definition
│   └── connector.py          # Connector implementation
└── documents/
    └── config.yml            # Configuration documents
```

---

**Note**: This reference is based on actual working templates. When in doubt, refer to existing templates in `dazn-templates` or `entain-templates` for more examples.
