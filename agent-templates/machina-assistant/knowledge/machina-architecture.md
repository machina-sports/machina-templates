# Machina Architecture Overview

## Technical Architecture

Machina is a platform for creating AI-powered sports content workflows. The stack relies on a three-tier architecture:

1. **Connectors**: Interfaces to external services (APIs, SDKs, Databases)
2. **Workflows**: Logic pipelines that chain tasks (Connector calls, Data transformations, Database ops)
3. **Agents**: Autonomous entities that execute Workflows based on triggers or schedules

## 1. Connectors

Connectors are the bridge between Machina and the outside world. They are defined in a specific directory structure under `connectors/`.

### Directory Structure
```
connectors/
└── <connector-name>/
    ├── <connector-name>.yml  # Definition
    └── <implementation>      # .py script or .json spec
```

### Connector Definition (.yml)
The YAML file defines the connector's identity and capabilities.

```yaml
connector:
  name: "my-custom-connector"
  description: "Description of what this connector does."
  filename: "my_script.py"    # The implementation file
  filetype: "pyscript"        # "pyscript" for Python, "restapi" for JSON-based REST wrappers
  commands:
    - name: "Command Name"    # Human readable name
      value: "function_name"  # Python function to call in 'filename'
```

### Implementation (pyscript)
For `pyscript` connectors, the Python file must contain functions that match the `value` defined in `commands`.

**Example (my_script.py):**
```python
def function_name(params):
    # params is a dictionary of inputs passed from the Workflow
    return {"result": "success", "data": params.get("input_key")}
```

### Implementation (restapi)
For `restapi` connectors, the `filename` points to a JSON file defining endpoints.

## 2. Workflows

Workflows are the core logic engines. They define a sequence of **Tasks**. Workflows are stateless pipelines that accept Inputs and produce Outputs.

### Workflow Definition (.yml)

```yaml
workflow:
  name: "my-workflow-name"
  title: "Workflow Title"
  description: "Logic description."
  
  # 1. Context Variables (Secrets & Env Vars)
  context-variables:
    my-connector-key: "$ENV_VAR_NAME"

  # 2. Global Inputs (JSONPath from trigger data)
  inputs:
    query: "$.get('query', 'default value')"

  # 3. Global Outputs (JSONPath from internal state)
  outputs:
    result: "$.get('final_result')"

  # 4. Tasks (The Logic)
  tasks:
    # ... tasks go here
```

### Task Types

#### A. Connector Task
Executes a command on a Connector.

```yaml
    - type: "connector"
      name: "task-name"
      connector:
        name: "my-custom-connector"     # Matches connector.name
        command: "function_name"        # Matches command value
      inputs:
        # Pass data to the connector function
        input_key: "$.get('query')"
      outputs:
        # Transform the result using Python Expressions
        # '$' represents the raw output from the connector
        raw_data: "$" 
        processed_data: |
          [
            { 'id': item.get('id'), 'val': item.get('value') * 2 }
            for item in $.get('items', [])
          ]
```

#### B. Document Task (Database)
Interacts with the Vector/Document database.

```yaml
    - type: "document"
      name: "save-data"
      condition: "$.get('processed_data') is not None" # Conditional execution
      config:
        action: "bulk-update"   # or "search"
        embed-vector: false     # Whether to generate embeddings
        force-update: true
      document_name: "collection_name"
      documents:
        items: "$.get('processed_data')"
```

#### C. Prompt Task (LLM)
Specialized task for sending prompts to LLM connectors.

```yaml
    - type: "prompt"
      name: "generate-text"
      connector:
        name: "openai"
        command: "invoke_prompt"
        model: "gpt-4o"
      inputs:
        messages: "$.get('chat_history')"
      outputs:
        response: "$.get('choices')[0].get('message').get('content')"
```

### Data Flow & JSONPath

Machina uses **JSONPath** (`$.get(...)`) extensively to access the Workflow's state.
- **Input**: Data flowing *into* a task is selected from the Workflow's current state using JSONPath.
- **Output**: Data returned *from* a task is merged back into the Workflow's state.
- **Inline Python**: The `outputs` block of a connector task allows running **inline Python code** (lists comprehensions, dict operations) to transform data immediately after receiving it. `$` refers to the connector's raw response.

## 3. Agents

Agents are the high-level "workers". They are configured via YAML and act as containers for Workflows. Agents govern **when** and **how** workflows are triggered.

### Agent Definition (.yml)

```yaml
agent:
  name: "my-agent"
  title: "My Agent Title"
  description: "What this agent does."
  context:
    config-frequency: 0.1   # Execution frequency/configuration
  workflows:
    - name: my-workflow-name    # Must match a workflow defined in the same template
      description: "Description of this workflow execution"
      inputs:
        # Maps Agent 'Context/State' to Workflow 'Inputs'
        input_status: "'waiting'"
      outputs:
        # Maps Workflow 'Outputs' back to Agent 'Context/State'
        workflow-status: "$.get('workflow-status')"
```

## Environment Variables

Environment variables use the `$MACHINA_CONTEXT_VARIABLE_` prefix followed by the service name:
- `$MACHINA_CONTEXT_VARIABLE_OPENAI_API_KEY`
- `$MACHINA_CONTEXT_VARIABLE_GROQ_API_KEY`
- `$MACHINA_CONTEXT_VARIABLE_PERPLEXITY_API_KEY`
- `$MACHINA_CONTEXT_VARIABLE_SPORTRADAR_SOCCER_V4_API_KEY`

## Available Connectors

### AI Services
- `openai`: OpenAI API integration
- `groq`: Groq API for fast inference
- `perplexity`: Perplexity API for web search
- `google-vertex`: Google Vertex AI integration
- `stability`: Stability AI for image generation

### Sports Data
- `api-football`: API-Football integration
- `sportradar-soccer`: Soccer data API
- `sportradar-nba`: NBA data API
- `sportradar-nfl`: NFL data API
- `sportradar-rugby`: Rugby data API
- `sportingbet`: Sports betting data

### Utilities
- `storage`: Data storage connector
- `machina-db`: Database connector
- `exa-search`: Search functionality
- `docling`: Document processing

