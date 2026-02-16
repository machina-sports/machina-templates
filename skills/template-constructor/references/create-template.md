---
description: Scaffold new Machina templates with correct YAML structure
---

# DevOps: Create Template

Scaffold new Machina templates with correct YAML structure.

## Trigger

- `/mkn-devops:create-template`
- "Create new template"
- "Scaffold agent template"

## Process

### 1. Gather Requirements

Ask user for:
- **Template name**: kebab-case identifier (e.g., `sports-predictions`)
- **Template type**: `agent-template` or `connector`
- **Target repo**: `dazn-templates`, `entain-templates`, or `machina-templates`
- **Components needed**: agents, workflows, prompts, mappings, connectors

### 2. Create Directory Structure

```bash
# For agent-template
mkdir -p agent-templates/template-name/{agents,workflows,prompts,mappings,scripts,documents}

# For connector
mkdir -p connectors/connector-name
```

### 3. Generate _install.yml

```yaml
setup:
  title: Template Name
  description: Brief description of what this template does
  category:
    - special-templates    # or: connectors, sports-data, etc.
  estimatedTime: 10 minutes
  features:
    - Feature 1
    - Feature 2
  integrations:
    - google-genai         # Required connectors
  status: available
  value: agent-templates/template-name
  version: 1.0.0

datasets:
  # Order matters - install dependencies first

  # Connectors (if any custom ones)
  - type: connector
    path: scripts/custom-connector.yml

  # Prompts
  - type: prompts
    path: prompts/main-prompts.yml

  # Mappings
  - type: mappings
    path: mappings/transformations.yml

  # Workflows
  - type: workflow
    path: workflows/main-workflow.yml

  # Agents (last - they depend on workflows)
  - type: agent
    path: agents/main-executor.yml
```

### 4. Generate Agent File

`agents/main-executor.yml`:

```yaml
agent:
  name: template-name-executor
  title: Template Name - Executor
  description: Main executor agent for template-name
  context:
    status: "inactive"
  context-agent:
    # Define input parameters from execution context
    messages: $.get('messages', [])
    thread_id: $.get('thread_id', None)
    # Add custom parameters as needed
  workflows:
    # First workflow - usually reasoning/analysis
    - name: template-name-reasoning
      description: Analyze input and determine action
      inputs:
        input_message: $.get('messages', [])
        thread_id: $.get('thread_id')
      outputs:
        reasoning: $.get('reasoning')
        document_id: $.get('document_id')

    # Main workflow - conditional execution
    - name: template-name-main
      description: Execute main logic
      condition: $.get('document_id') is not None
      inputs:
        document_id: $.get('document_id')
        reasoning: $.get('reasoning')
      outputs:
        result: $.get('result')

    # Response workflow - generate output
    - name: template-name-response
      description: Generate response
      condition: $.get('document_id') is not None
      inputs:
        document_id: $.get('document_id')
        result: $.get('result')
      outputs:
        response: $.get('response')
```

### 5. Generate Workflow File

`workflows/main-workflow.yml`:

```yaml
workflow:
  name: template-name-main
  title: Template Name - Main Workflow
  description: Main workflow for template-name
  context-variables:
    debugger:
      enabled: true
    google-genai:
      credential: $TEMP_CONTEXT_VARIABLE_VERTEX_AI_CREDENTIAL
      project_id: $TEMP_CONTEXT_VARIABLE_VERTEX_AI_PROJECT_ID
  inputs:
    document_id: $.get('document_id')
    reasoning: $.get('reasoning')
  outputs:
    result: $.get('result', {})
    workflow-status: $.get('success') is True and 'executed' or 'skipped'
  tasks:
    # Load document
    - type: document
      name: load-document
      description: Load the main document
      config:
        action: search
        search-limit: 1
        search-vector: false
      filters:
        document_id: $.get('document_id')
      outputs:
        document_exists: len($.get('documents', [])) > 0
        document_value: $.get('documents')[0].get('value', {}) if len($.get('documents', [])) > 0 else {}

    # Process with LLM
    - type: prompt
      name: process-prompt
      description: Process data with LLM
      condition: $.get('document_exists') is True
      connector:
        name: google-genai
        command: invoke_prompt
        model: gemini-3-flash-preview
        location: global
        provider: vertex_ai
      inputs:
        _0-document-data: $.get('document_value')
        _1-reasoning: $.get('reasoning')
      outputs:
        result: $

    # Save result
    - type: document
      name: save-result
      description: Save the result
      condition: $.get('result') is not None
      config:
        action: update
        embed-vector: false
        force-update: true
      documents:
        result: |
          {
            **$.get('document_value', {}),
            'result': $.get('result'),
            'processed_at': context.get('current_timestamp')
          }
      filters:
        document_id: $.get('document_id')
      outputs:
        success: True
```

### 6. Generate Prompt File

`prompts/main-prompts.yml`:

```yaml
prompts:
  - type: prompt
    name: template-name-analyzer
    title: Template Name - Analyzer
    description: Analyzes input to determine action
    instruction: |
      You receive the following inputs:
      - _0-document-data: The document data to analyze
      - _1-reasoning: Previous reasoning context

      Your task is to:
      1. Analyze the document data
      2. Determine the appropriate action
      3. Return structured output

      Rules:
      - Always provide a clear action recommendation
      - Include confidence score (0-100)
      - Explain your reasoning briefly
    schema:
      title: TemplateNameAnalyzer
      description: Analysis result
      type: object
      required: [action, confidence, explanation]
      properties:
        action:
          type: string
          enum: [process, skip, error]
          description: Recommended action
        confidence:
          type: integer
          minimum: 0
          maximum: 100
          description: Confidence in the recommendation
        explanation:
          type: string
          description: Brief explanation of the reasoning
```

### 7. Generate Mapping File (if needed)

`mappings/transformations.yml`:

```yaml
mappings:
  - type: mapping
    name: template-name-transform
    title: Template Name - Transform
    description: Transform input data
    outputs:
      transformed_data: |
        {
          'field1': $.get('input_field1', ''),
          'field2': $.get('input_field2', 0),
          'computed': len($.get('items', []))
        }
```

### 8. Generate Connector File (if custom logic needed)

`scripts/custom-connector.yml`:

```yaml
connector:
  name: template-name-processor
  description: Custom processor for template-name
  filename: custom-processor.py
  filetype: pyscript
  commands:
    - name: Process Data
      value: process_data
    - name: Validate Input
      value: validate_input
```

`scripts/custom-processor.py`:

```python
"""
Template Name - Custom Processor
"""

def process_data(context, inputs):
    """Process data with custom logic."""
    data = inputs.get('data', {})

    # Custom processing logic here
    result = {
        'processed': True,
        'data': data
    }

    return {
        'status': True,
        'data': result
    }

def validate_input(context, inputs):
    """Validate input data."""
    data = inputs.get('data', {})

    errors = []
    if not data.get('required_field'):
        errors.append('Missing required_field')

    return {
        'status': len(errors) == 0,
        'errors': errors
    }
```

## Template Type Examples

### Chat Agent (Conversation)

Use when you need a conversational agent:
- Thread management
- Message history
- Streaming responses

Reference: `dazn-templates/agent-templates/moderator-assistant`

### One-Shot Agent (No Thread)

Use for single-request processing:
- Auto-creates thread if needed
- No conversation state
- Quick responses

Reference: `dazn-templates/agent-templates/instructions-assistant`

### Periodic Agent (Scheduled)

Use for scheduled/recurring tasks:
- `config-frequency` in context
- Idempotency checks
- Batch processing

Reference: `machina-templates/agent-templates/power-ranking-periodic`

### Connector Only

Use for API integrations without agent logic:
- PyScript or REST API
- Reusable across templates

Reference: `machina-templates/connectors/google-genai`

## Example Interaction

```
User: Create a new template for sports predictions

Claude: I'll create a sports-predictions template. Let me gather some info:

1. Target repo? → dazn-templates
2. Components needed?
   - Agent: yes (chat-based predictions)
   - Workflows: yes (reasoning, prediction, response)
   - Prompts: yes (analyzer, predictor)
   - Connectors: no (use existing google-genai)

Creating structure:

dazn-templates/agent-templates/sports-predictions/
├── _install.yml
├── agents/
│   └── predictions-executor.yml
├── workflows/
│   ├── predictions-reasoning.yml
│   ├── predictions-generate.yml
│   └── predictions-response.yml
├── prompts/
│   └── predictions-prompts.yml
└── mappings/
    └── predictions-mappings.yml

[Creates all files with correct YAML structure]

Template created! Next steps:
1. Customize the prompts for your use case
2. Run /mkn-devops:validate-template to verify
3. Run /mkn-devops:install-template to deploy
```

## Related

- [Template YAML Reference](../.claude/guides/template-yaml-reference.md) - Complete YAML structure documentation
- [Validate Template](./validate-template.md) - Validate before installing
- [Install Template](./install-template.md) - Deploy templates
