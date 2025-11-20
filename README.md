# Machina Templates
Repository of templates and connectors for Machina Sports - a platform for creating AI-powered sports content workflows.

## Repository Structure

This repository is organized into two main directories:

### 1. Connectors
The `connectors` directory contains all the connectors used by the templates. Each connector follows a standardized naming convention:

- Directory name: `connectors/{connector-name}`
- Main files: `{connector-name}.{extension}`

### 2. Agent Templates
The `agent-templates` directory contains all the agent templates, organized by categories:

- Reporter templates (e.g., `reporter-briefing-en`, `reporter-image`, `reporter-polls-en`)
- Sport-specific templates (e.g., `sportingbet-nba`, `sportradar-soccer`)
- Brand-specific templates (e.g., `template-estelarbet`, `template-quizzes-dazn`)
- General templates (e.g., `chat-completion`)

## Naming Conventions

The repository follows these naming conventions:

### Connectors
Connectors use simple, descriptive names without prefixes:
- `openai` (previously `sdk-openai`)
- `groq` (previously `sdk-groq`)
- `perplexity` (previously `api-perplexity`)
- `sportradar-soccer` (previously `api-sportradar-soccer`)

### Environment Variables
Environment variables use the `$MACHINA_CONTEXT_VARIABLE_` prefix followed by the service name:
- `$MACHINA_CONTEXT_VARIABLE_OPENAI_API_KEY`
- `$MACHINA_CONTEXT_VARIABLE_GROQ_API_KEY`
- `$MACHINA_CONTEXT_VARIABLE_PERPLEXITY_API_KEY`
- `$MACHINA_CONTEXT_VARIABLE_SPORTRADAR_SOCCER_V4_API_KEY`

## Installation Instructions

To install a template:

1. Choose a template from the `agent-templates` directory
2. Make sure the required connectors are installed from the `connectors` directory
3. Configure the necessary environment variables in your Machina environment
4. Import the template workflows into your Machina instance

## Available Templates

The repository includes a wide range of templates for various sports content workflows:

### Reporter Templates
- `reporter-summary`: Generate game summaries
- `reporter-briefing-en/es`: Create pre-game briefings in English/Spanish
- `reporter-polls-en/es`: Generate interactive polls in English/Spanish
- `reporter-quizzes-en/es`: Create sports quizzes in English/Spanish
- `reporter-image`: Generate sports-related images
- `reporter-websearch`: Research web content for sports events
- `reporter-recap-pt-br`: Create post-game recaps in Portuguese

### Sport-Specific Templates
- `sportingbet-nba`: NBA-specific content workflows
- `sportradar-soccer`: Soccer data processing workflows
- `template-superbowl-lix`: NFL Super Bowl specific templates
- `kingpool-fantasy`: Fantasy sports content

### Brand-Specific Templates
- `template-estelarbet`: Templates for Estelarbet brand
- `template-quizzes-dazn`: Quiz templates for DAZN
- `sportingbet-blog`: Blog content for Sportingbet

### General Templates
- `chat-completion`: Generic chat completion workflows
- `template-quizzes`: Generic sports quiz templates

## Available Connectors

The repository includes connectors for various services:

### AI Services
- `openai`: OpenAI API integration
- `groq`: Groq API integration
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

## Technical Architecture

This guide serves as a technical reference for developers creating components within the Machina ecosystem. The stack relies on a three-tier architecture:

1.  **Connectors**: Interfaces to external services (APIs, SDKs, Databases).
2.  **Workflows**: Logic pipelines that chain tasks (Connector calls, Data transformations, Database ops).
3.  **Agents**: Autonomous entities that execute Workflows based on triggers or schedules.

### 1. Connectors

Connectors are the bridge between Machina and the outside world. They are defined in a specific directory structure under `connectors/`.

#### Directory Structure
```text
connectors/
└── <connector-name>/
    ├── <connector-name>.yml  # Definition
    └── <implementation>      # .py script or .json spec
```

#### Connector Definition (`.yml`)
The YAML file defines the connector's identity and capabilities.

**Reference: `connectors/openai/openai.yml`**

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

#### Implementation (`pyscript`)
For `pyscript` connectors, the Python file must contain functions that match the `value` defined in `commands`.

**Example (`my_script.py`):**
```python
def function_name(params):
    # params is a dictionary of inputs passed from the Workflow
    return {"result": "success", "data": params.get("input_key")}
```

#### Implementation (`restapi`)
For `restapi` connectors, the `filename` points to a JSON file defining endpoints.
*(Reference: `connectors/sportradar-nfl/sportradar-nfl.yml`)*

### 2. Agents

Agents are the high-level "workers". They are configured via YAML and act as containers for Workflows. Agents govern **when** and **how** workflows are triggered.

#### Agent Definition (`.yml`)
Agents are typically located in `agent-templates/<template-name>/<agent-name>.yml`.

**Reference: `agent-templates/nfl-2025-preseason/teams-agent.yml`**

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

### 3. Workflows

Workflows are the core logic engines. They define a sequence of **Tasks**. Workflows are stateless pipelines that accept Inputs and produce Outputs.

#### Workflow Definition (`.yml`)
Workflows are located in `agent-templates/<template-name>/<workflow-name>.yml`.

**Reference: `agent-templates/nfl-2025-preseason/sync-games.yml`**

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

#### Task Types

##### A. Connector Task
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

##### B. Document Task (Database)
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

##### C. Prompt Task (LLM)
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

#### Data Flow & JSONPath
Machina uses **JSONPath** (`$.get(...)`) extensively to access the Workflow's state.
*   **Input**: Data flowing *into* a task is selected from the Workflow's current state using JSONPath.
*   **Output**: Data returned *from* a task is merged back into the Workflow's state.
*   **Inline Python**: The `outputs` block of a connector task allows running **inline Python code** (lists comprehensions, dict operations) to transform data immediately after receiving it. `$` refers to the connector's raw response.

### 4. "Hello World" Tutorial

Create a simple system that echoes a message.

#### 1. Create Connector: `connectors/hello-world/hello.yml`
```yaml
connector:
  name: "hello-world"
  filename: "hello.py"
  filetype: "pyscript"
  commands:
    - name: "Say Hello"
      value: "say_hello"
```

#### 2. Create Script: `connectors/hello-world/hello.py`
```python
def say_hello(args):
    name = args.get("name", "World")
    return {"message": f"Hello, {name}!"}
```

#### 3. Create Workflow: `agent-templates/tutorial/hello-workflow.yml`
```yaml
workflow:
  name: "hello-flow"
  inputs:
    user_name: "$.get('name')"
  outputs:
    greeting: "$.get('final_message')"
  tasks:
    - type: "connector"
      name: "generate-greeting"
      connector:
        name: "hello-world"
        command: "say_hello"
      inputs:
        name: "$.get('user_name')"
      outputs:
        final_message: "$.get('message')"
```

#### 4. Create Agent: `agent-templates/tutorial/hello-agent.yml`
```yaml
agent:
  name: "greeter-bot"
  workflows:
    - name: hello-flow
      inputs:
        name: "'Developer'"
```

## Usage Examples

### Basic Workflow Structure
```yaml
workflow:
  name: "workflow-name"
  title: "Workflow Title"
  description: "Workflow description"
  context-variables:
    openai:
      api_key: "$MACHINA_CONTEXT_VARIABLE_OPENAI_API_KEY"
    sportradar-soccer:
      sportradar_api_key: "$MACHINA_CONTEXT_VARIABLE_SPORTRADAR_SOCCER_V4_API_KEY"
  inputs:
    event_code: "$.get('event_code') or None"
  outputs:
    workflow-status: "$.get('event-exists') is not True and 'skipped' or 'executed'"
  tasks:
    # Task definitions
```

## Contributing

To contribute to this repository:

1. Follow the established naming conventions
2. Ensure all environment variables use the `$MACHINA_CONTEXT_VARIABLE_` prefix
3. Document your templates and connectors thoroughly
4. Test your workflows before submitting
