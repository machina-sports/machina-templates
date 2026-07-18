# Prompt YAML Schema

Prompt definitions for structured LLM output. Prompts define the instruction text and JSON Schema that the LLM must follow.

**Location**: `agent-templates/<template-name>/prompts/<prompt-name>.yml`

---

## Root Structure

There are two valid root formats:

### Format 1: Array (preferred, supports multiple prompts per file)

```yaml
prompts:
  - type: prompt
    name: <string>           # Required. Unique identifier (kebab-case)
    title: <string>          # Required. Human-readable title
    description: <string>    # Optional. What this prompt does
    instruction: <string>    # Required. LLM instruction text (multiline)
    schema: <object>         # Required. JSON Schema for structured output
```

### Format 2: Single prompt (legacy, still supported)

```yaml
prompt:
  name: <string>
  title: <string>
  description: <string>
  instructions: <string>     # Note: "instructions" (plural) in this format
  schema: <object>
```

**Prefer Format 1** (`prompts:` array with `instruction:` singular). Format 2 uses `instructions:` (plural) and `prompt:` (singular root).

---

## Field Reference

### `name` (required)

Unique identifier. Must match the `name` field in the workflow's prompt task.

```yaml
name: assistant-chat-reasoning-prompt
```

### `title` (required)

```yaml
title: Assistant Chat | Reasoning Prompt
```

### `description` (optional)

```yaml
description: Analyzes user messages to determine intent and extract event information
```

### `instruction` / `instructions` (required)

The LLM instruction text. Always use multiline pipe `|`.

**In `prompts:` array format**: use `instruction:` (singular)
**In `prompt:` single format**: use `instructions:` (plural)

```yaml
instruction: |
  Analyze the user's messages to determine intent.

  CONTEXT-AWARE DETECTION:
  - If user mentions a specific team, extract match info
  - Always prioritize upcoming matches

  RULES:
  1. Extract team names using full names
  2. Format as "Team A vs Team B"
  3. Never use placeholders
```

**Variable references in instructions**: Use `{{variable_name}}` syntax to reference input variables.

```yaml
instructions: |
  You are a master roaster creating a viral tweet roasting {{team_b}}
  from {{team_a}}'s perspective.

  CONTEXT:
  - Team A: {{team_a}} (the roaster)
  - Team B: {{team_b}} (getting roasted)
  - Intensity: {{roast_intensity}}
  - Language: {{language}}
  - Search Results: {{search_response}}
```

**Note on variables**: When a prompt task uses `_N-` prefixed inputs (e.g., `_1-conversation-history`), the prompt sees them by their full name. The LLM receives the inputs as context alongside the instruction.

### `schema` (required)

JSON Schema defining the structured output the LLM must return.

```yaml
schema:
  title: SchemaName
  description: What this schema represents
  type: object
  required: [field1, field2]
  properties:
    field1:
      type: string
      description: What this field contains
    field2:
      type: boolean
      description: Whether something is true
```

---

## Schema Property Types

### `string`

```yaml
search_query:
  type: string
  description: "Search query for knowledge base"

# With enum constraint
response_type:
  type: string
  enum: ["tutorial", "explanation", "code_example", "reference", "troubleshooting"]
  description: "Best format to answer the question"

# With max length
roast_content:
  type: string
  maxLength: 280
  description: "Tweet-length roast - max 280 characters"

# With format
start_date:
  type: string
  format: date
  description: "Start date in YYYY-MM-DD format"
```

### `boolean`

```yaml
is_search_request:
  type: boolean
  description: "True if user is looking for existing events"
```

### `integer`

```yaml
confidence:
  type: integer
  minimum: 0
  maximum: 100
  description: "Confidence in the recommendation"

id:
  type: integer
  description: "Source ID"
```

### `number`

```yaml
odd_from:
  type: number
  description: "Minimum odds value for filtering"

target_odd:
  type: number
  description: "Target total odd for combined bet"
```

### `array`

```yaml
# Array of strings
search_queries:
  type: array
  description: "Array of 5 search queries"
  minItems: 5
  maxItems: 5
  items:
    type: string
    description: "Search query for sports content"

# Array of strings (simple)
key_topics:
  type: array
  items:
    type: string
  description: "List of key topics mentioned"

# Array of strings (hashtags)
hashtags:
  type: array
  items:
    type: string
  description: "Relevant hashtags (5-8)"

# Array of objects
roast_points:
  type: array
  description: "3 alternative tweet roasts"
  items:
    type: object
    properties:
      id:
        type: integer
        description: "Variation number"
      content:
        type: string
        maxLength: 280
        description: "Alternative roast"
      source_references:
        type: array
        items:
          type: integer
        description: "Source IDs supporting this roast"

# Array of integers
source_references:
  type: array
  items:
    type: integer
  description: "Source IDs"
```

### `object`

```yaml
# Nested object
search_date_interval:
  type: object
  description: "Date range for filtering events"
  properties:
    start_date:
      type: string
      format: date
      description: "Start date in YYYY-MM-DD"
    end_date:
      type: string
      format: date
      description: "End date in YYYY-MM-DD"
  required: ["start_date", "end_date"]

# Object with free-form content
image_content:
  type: object
  description: "Structured data for image generation"
```

---

## Pattern Examples

### Simple Reasoning Prompt (boolean flags + enum)

```yaml
prompts:
  - type: prompt
    name: machina-assistant-reasoning-prompt
    title: Machina Assistant | Reasoning Prompt
    description: Analyzes user messages to determine intent
    instruction: |
      Review the conversation history and user messages.

      INTENT CLASSIFICATION:
      1. ARCHITECTURE - questions about connectors, workflows, agents
      2. DEPLOYMENT - environment config, Docker, scaling
      3. GENERAL - getting started, overview, best practices

      RESPONSE TYPE:
      - "tutorial": Step-by-step guide
      - "explanation": Conceptual
      - "code_example": YAML/code examples

      SHORT MESSAGE:
      Brief status message while searching.
    schema:
      title: MachinaAssistantReasoning
      type: object
      required: [is_architecture_question, response_type, search_query, short_message]
      properties:
        is_architecture_question:
          type: boolean
          description: "User asks about architecture"
        response_type:
          type: string
          enum: ["tutorial", "explanation", "code_example", "reference", "troubleshooting"]
        search_query:
          type: string
          description: "Natural language query for knowledge base"
        short_message:
          type: string
          description: "Brief status message"
```

### Content Generation Prompt (string output + array)

```yaml
prompt:
  name: personalized-podcast-generate-search-queries
  title: Generate Search Queries
  description: "Generate search queries for sports content based on user preferences"
  instructions: |
    Generate exactly 5 Google Search queries for sports content.

    Use the provided parameters:
    - favorite_sport: The sport the user follows
    - favorite_team: The entity the user follows
    - sports_knowledge: User's knowledge level
    - language: Language for the queries

    CRITICAL: Always use the exact favorite_team value provided.
    PRIORITY: Focus on most recent updates and latest news.
  schema:
    title: PersonalizedPodcastGenerateSearchQueries
    type: object
    required: [search_queries]
    properties:
      search_queries:
        type: array
        description: "Array of 5 search queries"
        minItems: 5
        maxItems: 5
        items:
          type: string
```

### Complex Schema (nested objects + arrays of objects)

```yaml
prompt:
  name: roast-agent-generate-roast-prompt
  title: Roast Agent Generate Viral Tweet
  description: "Generate tweet-length roast with source citations"
  instructions: |
    Create ONE hyper viral tweet roasting {{team_b}} from {{team_a}}'s perspective.

    TWEET REQUIREMENTS:
    - MAXIMUM 280 CHARACTERS
    - Include ONE specific fact from search results
    - Must be screenshot-worthy
  schema:
    title: RoastAgentGenerateRoast
    type: object
    required: [roast_content, roast_points, headline, sources]
    properties:
      roast_content:
        type: string
        maxLength: 280
        description: "THE viral tweet roast"
      roast_points:
        type: array
        description: "3 alternative tweet roasts"
        items:
          type: object
          properties:
            id:
              type: integer
            content:
              type: string
              maxLength: 280
            source_references:
              type: array
              items:
                type: integer
      headline:
        type: string
        maxLength: 60
        description: "Punchy headline (max 8 words)"
      sources:
        type: array
        items:
          type: object
          properties:
            id:
              type: integer
            url:
              type: string
            title:
              type: string
            explanation:
              type: string
            data_points:
              type: array
              items:
                type: string
```

---

## How Prompts Connect to Workflow Tasks

A workflow prompt task references a prompt by `name` and passes inputs:

```yaml
# In workflow YAML
- type: prompt
  name: machina-assistant-reasoning-prompt    # Must match prompt name
  connector:
    name: google-genai
    command: invoke_prompt
    model: gemini-2.5-flash
    location: global
    provider: vertex_ai
  inputs:
    _1-conversation-history: $.get('messages', [])[-5:]
    _2-user-messages: $.get('input_message')
  outputs:
    reasoning: $    # Entire structured response
```

**Input prefix ordering**: `_1-`, `_2-`, etc. control the order variables appear in the prompt context. The engine strips the prefix and passes the value.

| Workflow input key | Prompt sees |
|-------------------|-------------|
| `_1-conversation-history` | `conversation-history` (ordered first) |
| `_2-user-messages` | `user-messages` (ordered second) |

**Unprefixed inputs** are also valid and passed as-is:

```yaml
inputs:
  team_a: $.get('team_a')
  team_b: $.get('team_b')
  language: $.get('language', 'en')
```

---

## Naming Conventions

| Element | Convention | Example |
|---------|-----------|---------|
| Prompt name | `<template>-<purpose>-prompt` or `<template>-<purpose>` | `assistant-chat-reasoning-prompt` |
| Schema title | PascalCase | `MachinaAssistantReasoning` |
| Properties | snake_case | `is_find_event`, `search_query` |

---

## Common Mistakes

| Mistake | Correct |
|---------|---------|
| `prompt:` with `instruction:` | `prompt:` uses `instructions:` (plural) |
| `prompts:` with `instructions:` | `prompts:` array uses `instruction:` (singular) |
| `messages:` instead of `instruction:` | Use `instruction:` (or `instructions:` for singular format) |
| Missing `schema` | Every prompt needs a `schema` for structured output |
| `schema.type` missing | Always include `type: object` at schema root |
| `required` as object | `required` is an array of field names |
| `properties` without `type` on each | Every property needs a `type` field |
| Prompt name mismatch | Workflow task `name` must exactly match prompt `name` |
| Array items without `type` | `items:` must have at least `type` defined |
