# Init

Scaffold a new Machina template project from scratch with directory structure, configuration files, and documentation.

## Trigger

- `/mkn-templates:init-template`
- "Init template", "Initialize new template", "Scaffold new template project"

## Process

### 1. Gather Requirements

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| **template_name** | Yes | — | kebab-case (e.g., `my-custom-agent`) |
| **template_type** | Yes | `agent-templates` | `agent-templates` or `connectors` |
| **target_repo** | Yes | — | Repository path |
| **title** | Yes | — | Human-readable title |
| **description** | Yes | — | Brief description |
| **category** | No | `["special-templates"]` | Template categories |
| **integrations** | No | `["machina-ai"]` | Required connectors |
| **version** | No | `1.0.0` | Initial version |

### 2. Validate Inputs

1. **Template name**: lowercase, hyphens only (`^[a-z0-9-]+$`)
2. **Target repo exists**: path must be valid
3. **Template does not already exist**: no overwriting
4. **Template type directory exists**: create if needed

### 3. Create Directory Structure

```bash
# Agent template
mkdir -p {repo}/agent-templates/{name}/{agents,workflows,prompts,mappings,scripts,setup}

# Connector
mkdir -p {repo}/connectors/{name}
```

### 4. Generate `_install.yml`

> Schema reference: [setup.md](../schemas/setup.md) Part 1

```yaml
setup:
  title: "{title}"
  description: "{description}"
  category:
    - {category}
  estimatedTime: 10 minutes
  features:
    - {description}
  integrations:
    - {integrations}
  status: available
  value: {template_type}/{template_name}
  version: {version}

datasets:
  - type: "documents"
    path: "setup/_index.yml"
  - type: "prompts"
    path: "prompts/main-prompts.yml"
  - type: "workflow"
    path: "workflows/main-workflow.yml"
  - type: "workflow"
    path: "_folders.yml"
  - type: "agent"
    path: "_setup.yml"
  - type: "agent"
    path: "agents/main-executor.yml"
```

### 5. Generate `setup/_index.yml`

> Schema reference: [setup.md](../schemas/setup.md) Part 2

```yaml
documents:
  - name: "{template_name}-config"
    title: "{title} Config"
    filename: "config.json"
    filetype: json
    metadata:
      category: config
      template: "{template_name}"
```

And the corresponding `setup/config.json`:

```json
{
  "title": "{title} Configuration",
  "enabled": true
}
```

### 6. Generate `_folders.yml`

Folder/document setup workflow (boilerplate — not in schemas):

```yaml
workflow:
  name: "{template_name}-folders"
  title: "{title} | Setup Folders"
  description: "Setup Folders"
  inputs:
    force-setup: "$.get('force-setup') == 'true'"
  outputs:
    setup-register: "$.get('setup-register')"
    workflow-status: "($.get('setup-register') is True or $.get('force-setup') is True) and 'skipped' or 'executed'"
  tasks:

    - type: "document"
      name: "load-setup-register"
      description: "Search for setup-register"
      config:
        action: "search"
        search-limit: 1
        search-vector: false
      inputs:
        name: "'setup-register'"
      outputs:
        setup-register: "$.get('documents')[0].get('value').get('setup', False) if $.get('documents') else False"

    - type: "document"
      name: "{template_name}-install-documents"
      description: "Install documents."
      condition: "$.get('setup-register') is not True or $.get('force-setup') is True"
      config:
        action: "update"
        embed-vector: false
        force-update: true
      documents:
        setup-playground: |
          [
            {
              "title": "{title}",
              "name": "{template_name}-main",
            }
          ]
        setup-register: |
          {
            "setup": True
          }
        site-structure: |
          [
          ]
        doc-structure: |
          [
            {
              "title": "Catalogue",
              "isActive": True,
              "icon": "folder",
              "items": [
                {
                  "name": "documents",
                  "title": "Documents",
                  "description": "Configuration documents.",
                  "category": "Catalogue",
                  "metadata": {
                    "name": ["{template_name}-document"]
                  },
                  "sorters": ['_id', -1],
                  "view": "list"
                }
              ]
            }
          ]
```

### 7. Generate `_setup.yml`

Setup agent that runs the folders workflow (boilerplate):

```yaml
agent:
  name: "setup-{template_name}"
  title: "Setup {title}"
  description: "Setup {title}"
  context:
    config-frequency: 99999999
  workflows:
    - name: "{template_name}-folders"
      description: "Setup Folders"
      condition: "$.get('setup-register') is not True"
      outputs:
        setup-register-status: "$.get('workflow-status', False)"
```

### 8. Generate Stub Files

> Schema references: [agent.md](../schemas/agent.md) · [prompt.md](../schemas/prompt.md) · [workflow.md](../schemas/workflow.md)

#### `agents/main-executor.yml`

```yaml
agent:
  name: "{template_name}-executor"
  title: "{title} - Executor"
  description: "{description}"
  context:
    status: "inactive"
  context-agent:
    messages: "$.get('messages', [])"
    thread_id: "$.get('thread_id', None)"
  workflows:
    - name: "{template_name}-main-workflow"
      description: "Main workflow"
      inputs:
        input_message: "$.get('messages', [])"
        thread_id: "$.get('thread_id')"
      outputs:
        response: "$.get('response')"
```

#### `prompts/main-prompts.yml`

```yaml
prompts:
  - type: "prompt"
    name: "{template_name}-analyzer"
    title: "{title} - Analyzer"
    description: "Analyzes input and generates response."
    instruction: |
      You are {title}. {description}

      You receive the following inputs:
      - _0-input-data: The user input data

      Your task is to:
      1. Analyze the input data
      2. Generate an appropriate response
    schema:
      title: "{template_name}Analyzer"
      description: "Analysis result"
      type: object
      required: [response]
      properties:
        response:
          type: string
          description: "The generated response"
```

#### `workflows/main-workflow.yml`

```yaml
workflow:
  name: "{template_name}-main-workflow"
  title: "{title} - Main Workflow"
  description: "Main workflow for {template_name}"
  context-variables:
    debugger:
      enabled: true
    machina-ai:
      credential: "$TEMP_CONTEXT_VARIABLE_MACHINA_AI_API_KEY"
  inputs:
    input_message: "$.get('input_message', [])"
    thread_id: "$.get('thread_id')"
  outputs:
    response: "$.get('response', '')"
    workflow-status: "$.get('response') is not None and 'executed' or 'skipped'"
  tasks:
    - type: "prompt"
      name: "{template_name}-process"
      description: "Process input with LLM"
      connector:
        name: "machina-ai"
        command: "invoke_prompt"
        model: "machina-ai"
      inputs:
        _0-input-data: "$.get('input_message')"
      outputs:
        response: "$"
```

### 9. Generate Documentation

Create `README.md` and `CHANGES.md` with template metadata.

### 10. Display Summary

```
Template initialized!

{repo}/agent-templates/{name}/
├── _install.yml           # Installation manifest
├── _folders.yml           # Folder/document setup
├── _setup.yml             # Setup agent
├── README.md
├── CHANGES.md
├── agents/main-executor.yml
├── prompts/main-prompts.yml
├── workflows/main-workflow.yml
├── setup/
│   ├── _index.yml
│   └── config.json
├── scripts/               # (empty)
└── mappings/              # (empty)

Next steps:
1. Edit prompts and workflows for your use case
2. /mkn-templates:validate to verify syntax
3. /mkn-templates:install to deploy
```

## Differences from `create`

| Aspect | `init` | `create` |
|--------|--------|----------|
| **Focus** | Full project scaffold with docs | Individual YAML components |
| **Creates** | Everything + `_folders.yml`, `_setup.yml`, README | Agent, workflow, prompt, mapping files |
| **When to use** | Starting a new template from scratch | Adding components to an existing template |

## Related

- [Create](./create.md) — Scaffold individual YAML components
- [Validate](./validate.md) — Validate before installing
- [Install](./install.md) — Deploy templates
- [Analyze](./analyze.md) — Inspect template structure
