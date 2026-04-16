# Connector YAML Schema

Connectors are external service integrations — either Python scripts or REST API specs. They bridge workflows to APIs, LLMs, databases, and other services.

**Location**: `connectors/<connector-name>/<connector-name>.yml`

---

## Root Structure

```yaml
connector:
  name: <string>            # Required. Unique identifier (kebab-case)
  description: <string>     # Required. What this connector does
  filename: <string>        # Required. Implementation file name
  filetype: <string>        # Required. "pyscript" or "restapi"
  commands: <list>          # Required for pyscript. Command definitions
```

---

## Field Reference

### `name` (required)

Unique identifier. Referenced in workflow `context-variables` and task `connector.name`.

```yaml
name: google-genai
```

### `description` (required)

```yaml
description: "Bwin Sports API - Access fixtures, competitions, odds and live scoreboards"
```

### `filename` (required)

The implementation file, relative to the connector directory.

```yaml
# Python script
filename: google-genai.py

# REST API spec
filename: bwin.json
```

### `filetype` (required)

Implementation type. Determines how the engine executes the connector.

| Value | Description | `filename` extension |
|-------|-------------|---------------------|
| `pyscript` | Python script with command functions | `.py` |
| `restapi` | OpenAPI/Swagger JSON specification | `.json` |

```yaml
filetype: pyscript
filetype: restapi
```

### `commands` (required for pyscript)

List of callable commands. Each command maps a display name to a Python function.

```yaml
commands:
  - name: "Prompt"
    value: "invoke_prompt"
  - name: "Web Search"
    value: "invoke_search"
  - name: "Image"
    value: "invoke_image"
  - name: "Video"
    value: "invoke_video"
```

| Field | Description |
|-------|-------------|
| `name` | Human-readable display name |
| `value` | Python function name in the `.py` file |

**Note**: REST API connectors (`restapi`) don't need `commands` — endpoints are defined in the JSON spec.

---

## Connector Types

### PyScript Connector

Python script with self-contained command functions.

**YAML definition**:

```yaml
connector:
  name: elevenlabs
  description: "The ElevenLabs connector for text-to-speech."
  filename: elevenlabs.py
  filetype: pyscript
  commands:
    - name: "get_text_to_speech"
      value: "get_text_to_speech"
    - name: "get_voices"
      value: "get_voices"
```

**Python implementation** (`elevenlabs.py`):

```python
def get_text_to_speech(request_data):
    headers = request_data.get("headers", {})
    params = request_data.get("params", {})
    path_attr = request_data.get("path_attribute", {})

    api_key = headers.get("api_key") or params.get("api_key", "")
    text = path_attr.get("text")

    # ... implementation ...

    return {"status": True, "data": result}

def get_voices(request_data):
    headers = request_data.get("headers", {})
    api_key = headers.get("api_key", "")

    # ... implementation ...

    return {"status": True, "voices": voices_list}
```

**Function signature**: Every command function receives a single `request_data` dict with:

| Key | Description |
|-----|-------------|
| `headers` | Credentials from `context-variables` (api_key, credential, etc.) |
| `params` | Values from workflow task `inputs` |
| `path_attribute` | Additional parameters (varies by connector) |

### REST API Connector

OpenAPI/Swagger JSON specification. The engine auto-generates commands from the API paths.

**YAML definition** (minimal):

```yaml
connector:
  name: api-football
  description: "API Football API"
  filename: api-football.json
  filetype: restapi
```

**JSON spec** (`api-football.json`): Standard OpenAPI 3.0 format.

```json
{
  "openapi": "3.0.1",
  "info": {
    "title": "API Football",
    "version": "v3"
  },
  "servers": [
    {"url": "https://v3.football.api-sports.io"}
  ],
  "paths": {
    "/fixtures": {
      "get": {
        "summary": "Get fixtures",
        "operationId": "GetFixtures",
        "parameters": [...]
      }
    }
  }
}
```

Commands are derived from `operationId` or path. In workflow tasks, the `command` field uses the path:

```yaml
# In workflow task
connector:
  name: api-football
  command: get-fixtures       # Maps to /fixtures GET
```

---

## Python Implementation Constraints

**Critical rules** for PyScript connectors:

1. **No helper functions outside command functions**. The engine only executes the named function — any module-level functions are invisible and will break.

```python
# WRONG — helper at module level
def _format_response(data):
    return {"formatted": data}

def invoke_prompt(request_data):
    return _format_response(result)  # Will fail

# CORRECT — helper inside command function
def invoke_prompt(request_data):
    def _format_response(data):
        return {"formatted": data}
    return _format_response(result)
```

2. **No module-level constants**. Move shared constants to a separate `setup.py` file.

```python
# WRONG — constant at module level
API_BASE_URL = "https://api.example.com"

# CORRECT — import from setup.py
from setup import API_BASE_URL
```

3. **Each command function must be fully self-contained**: imports, constants (via `from setup import ...`), and all logic inside the function body.

4. **`setup.py` pattern**: Use a `setup.py` file in the same directory for shared configuration.

```python
# setup.py
API_BASE_URL = "https://api.example.com"
DEFAULT_MODEL = "gpt-4o"
SUPPORTED_FORMATS = ["mp3", "wav"]

# connector.py
def invoke_prompt(request_data):
    from setup import API_BASE_URL, DEFAULT_MODEL
    # ... use constants ...
```

---

## Examples

### AI Service Connector (multiple commands)

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

### LLM Wrapper Connector

```yaml
connector:
  name: machina-ai
  description: "This connector is the Machina AI connector."
  filename: machina-ai.py
  filetype: pyscript
  commands:
    - name: "Embedding"
      value: "invoke_embedding"
    - name: "Prompt"
      value: "invoke_prompt"
    - name: "Prompt"
      value: "transcribe_audio_to_text"
```

### Sports Data REST API

```yaml
connector:
  name: sportradar-nfl
  description: "Sportradar NFL API v7"
  filename: sportradar-nfl.json
  filetype: restapi
```

### RSS Feed Connector

```yaml
connector:
  name: rss-feed
  description: "A robust connector for fetching and parsing RSS and Atom feeds."
  filename: rss-feed.py
  filetype: pyscript
  commands:
    - name: "Fetch Feed"
      value: "fetch_feed"
    - name: "Fetch Items"
      value: "fetch_items"
```

---

## How Connectors Are Used in Workflows

### 1. Declare credentials in `context-variables`

```yaml
workflow:
  context-variables:
    google-genai:
      credential: $TEMP_CONTEXT_VARIABLE_VERTEX_AI_CREDENTIAL
      project_id: $TEMP_CONTEXT_VARIABLE_VERTEX_AI_PROJECT_ID
```

### 2. Reference in task `connector` block

```yaml
- type: prompt
  connector:
    name: google-genai
    command: invoke_prompt
    model: gemini-2.5-flash
```

Or for connector tasks:

```yaml
- type: connector
  connector:
    name: api-football
    command: get-fixtures
  inputs:
    id: "$.get('event_id')"
```

---

## Naming Conventions

| Element | Convention | Example |
|---------|-----------|---------|
| Connector name | kebab-case, service name | `google-genai`, `api-football` |
| Python filename | matches connector name | `google-genai.py` |
| JSON filename | matches connector name | `api-football.json` |
| Command `value` | snake_case function name | `invoke_prompt`, `fetch_feed` |
| Command `name` | Human-readable | `"Prompt"`, `"Fetch Feed"` |

---

## Common Mistakes

| Mistake | Correct |
|---------|---------|
| `type: pyscript` | `filetype: pyscript` |
| `script: file.py` | `filename: file.py` |
| `filetype: python` | `filetype: pyscript` |
| `filetype: json` | `filetype: restapi` (for API specs) |
| Helper functions at module level | Put helpers inside command functions |
| Module-level constants | Use `setup.py` for shared constants |
| Missing `commands` for pyscript | Required — engine needs to know callable functions |
| `commands` for restapi | Not needed — derived from JSON spec |
