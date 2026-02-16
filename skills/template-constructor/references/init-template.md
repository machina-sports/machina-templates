---
description: Initialize new Machina template with directory structure and configuration files
---

# DevOps: Init Template

Scaffold a new Machina template project from scratch with the proper directory structure, configuration files, and documentation.

## Trigger

- `/mkn-templates:init-template`
- "Init template [name]"
- "Initialize new template"
- "Scaffold new template project"

## Process

### 1. Gather Requirements

Ask user for the following (provide defaults where possible):

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| **template_name** | Yes | - | kebab-case name (e.g., `my-custom-agent`) |
| **template_type** | Yes | `agent-templates` | One of: `agent-templates`, `connectors` |
| **target_repo** | Yes | - | Repository path (e.g., `/Users/fernando/machina/dazn-templates`) |
| **title** | Yes | - | Human-readable title (e.g., "My Custom Agent") |
| **description** | Yes | - | Brief description of what the template does |
| **category** | No | `["special-templates"]` | Template categories |
| **integrations** | No | `["machina-ai"]` | Required connectors |
| **version** | No | `1.0.0` | Initial version |

### 2. Validate Inputs

Before creating anything, verify:

1. **Template name format**: lowercase, hyphens only (`^[a-z0-9-]+$`)
2. **Target repo exists**: `ls {target_repo}` must succeed
3. **Template does not already exist**: `{target_repo}/{template_type}/{template_name}` must NOT exist
4. **Template type directory exists**: `{target_repo}/{template_type}` must exist (or create it)

### 3. Create Directory Structure

For `agent-templates`:

```bash
mkdir -p {target_repo}/agent-templates/{template_name}/agents
mkdir -p {target_repo}/agent-templates/{template_name}/prompts
mkdir -p {target_repo}/agent-templates/{template_name}/workflows
mkdir -p {target_repo}/agent-templates/{template_name}/scripts
mkdir -p {target_repo}/agent-templates/{template_name}/mappings
```

For `connectors`:

```bash
mkdir -p {target_repo}/connectors/{template_name}
```

### 4. Generate `_install.yml`

Write the installation manifest with the gathered metadata:

```yaml
setup:
  title: "{title}"
  description: {description}
  category:
    - {category[0]}
  estimatedTime: 10 minutes
  features:
    - {description}
  integrations:
    - {integrations[0]}
  status: available
  value: {template_type}/{template_name}
  version: {version}

datasets:

  # prompts
  - type: "prompts"
    path: "prompts/main-prompts.yml"

  # workflows
  - type: "workflow"
    path: "workflows/main-workflow.yml"

  # folders setup
  - type: "workflow"
    path: "_folders.yml"

  # agent setup
  - type: "agent"
    path: "_setup.yml"

  # main agent
  - type: "agent"
    path: "agents/main-executor.yml"
```

### 5. Generate `_folders.yml`

Write the folder/document setup workflow:

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

    # load-setup-register
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

    # documents-structure
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

### 6. Generate `_setup.yml`

Write the setup agent that runs the folders workflow:

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

### 7. Generate Stub Files

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

      Rules:
      - Always provide a helpful response
      - Be concise and accurate
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

    # Process with LLM
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

### 8. Generate Documentation Files

#### `README.md`

```markdown
# {title}

{description}

## Installation

\`\`\`
/mkn-templates:install-template
# Source: {target_repo}/{template_type}/{template_name}
\`\`\`

## Structure

- **agents/**: Agent executor definitions
- **prompts/**: LLM prompt configurations
- **workflows/**: Workflow definitions
- **scripts/**: Custom connectors
- **mappings/**: Data transformation mappings

## Configuration

- `_install.yml` - Installation manifest and dataset order
- `_folders.yml` - UI folder/document structure setup
- `_setup.yml` - Setup agent (runs folders workflow)

## Version

v{version}

See [CHANGES.md](CHANGES.md) for version history.
See [ROADMAP.md](ROADMAP.md) for planned features.
```

#### `CHANGES.md`

```markdown
# Changelog

## [{version}] - {today_date}

### Added
- Initial template scaffold
- Basic agent executor
- Main workflow with LLM integration
- Prompt templates
- Folder structure configuration
- Documentation
```

#### `ROADMAP.md`

```markdown
# Roadmap - {title}

## Version {next_version} (Planned)
- [ ] Implement core agent logic
- [ ] Add specialized prompts
- [ ] Add data workflows
- [ ] Add unit tests

## Version 2.0.0 (Planned)
- [ ] Advanced features
- [ ] Performance optimization
- [ ] Extended documentation
```

### 9. Display Summary

After creating all files, display:

```
Template initialized successfully!

{target_repo}/{template_type}/{template_name}/
├── _install.yml           # Installation manifest
├── _folders.yml           # Folder/document setup
├── _setup.yml             # Setup agent
├── README.md              # Documentation
├── CHANGES.md             # Changelog
├── ROADMAP.md             # Development roadmap
├── agents/
│   └── main-executor.yml  # Main agent executor
├── prompts/
│   └── main-prompts.yml   # LLM prompts
├── workflows/
│   └── main-workflow.yml  # Main workflow
├── scripts/               # (empty - add custom connectors)
└── mappings/              # (empty - add data mappings)

Next steps:
1. Edit prompts/main-prompts.yml with your specific prompt instructions
2. Edit workflows/main-workflow.yml with your processing logic
3. Run /mkn-templates:validate-template to verify YAML syntax
4. Run /mkn-templates:install-template to deploy
```

## Differences from `create-template`

| Aspect | `create-template` | `init-template` |
|--------|-------------------|-----------------|
| **Focus** | YAML file content with correct patterns | Full project scaffold with docs |
| **Creates** | Agent, workflow, prompt, mapping YAML files | Everything + `_install.yml`, `_folders.yml`, `_setup.yml`, README, CHANGES, ROADMAP |
| **When to use** | Adding components to an existing template | Starting a brand new template from scratch |
| **Output** | Individual YAML files | Complete ready-to-install project structure |

## Example Interaction

```
User: /mkn-templates:init-template

Claude: I'll help you initialize a new template. Let me gather some info:

1. Template name? → sports-predictions
2. Template type? → agent-templates
3. Target repo? → /Users/fernando/machina/dazn-templates
4. Title? → Sports Predictions
5. Description? → AI-powered sports predictions engine
6. Integrations? → machina-ai, google-genai

Creating template structure...

dazn-templates/agent-templates/sports-predictions/
├── _install.yml
├── _folders.yml
├── _setup.yml
├── README.md
├── CHANGES.md
├── ROADMAP.md
├── agents/main-executor.yml
├── prompts/main-prompts.yml
├── workflows/main-workflow.yml
├── scripts/
└── mappings/

Template initialized! 11 files created.

Next steps:
1. Customize prompts and workflows
2. /mkn-templates:validate-template to check syntax
3. /mkn-templates:install-template to deploy
```

## Related

- [Create Template](./create-template.md) - Scaffold individual YAML components
- [Validate Template](./validate-template.md) - Validate before installing
- [Install Template](./install-template.md) - Deploy templates
- [Analyze Template](./analyze-template.md) - Inspect template structure
