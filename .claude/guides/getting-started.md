# Getting Started with Machina Templates

This guide helps you get started creating and using Machina templates.

## What are Machina Templates?

Machina templates are reusable packages containing:
- **Agents** - Orchestrators that execute workflows
- **Workflows** - Task sequences that process data
- **Prompts** - LLM instructions with structured outputs
- **Mappings** - Data transformations
- **Connectors** - External API integrations

## Quick Start

### 1. Install a Template

Use the `/mkn-templates:install-template` skill to install templates:

```bash
/mkn-templates:install-template
```

Or install via MCP:

```python
mcp__docker_localhost__import_templates_from_git(
    repositories=[{
        "repo_url": "https://github.com/machina-sports/machina-templates",
        "template": "agent-templates/chat-completion",
        "repo_branch": "main"
    }]
)
```

### 2. Create a New Template

Use the `/mkn-templates:create-template` skill:

```bash
/mkn-templates:create-template
```

This scaffolds a complete template structure:

```
my-template/
├── _install.yml          # Installation manifest
├── agents/
│   └── executor.yml      # Agent definition
├── workflows/
│   └── main.yml          # Workflow definition
├── prompts/
│   └── reasoning.yml     # Prompt definitions
└── mappings/
    └── transform.yml     # Data transformations
```

### 3. Validate Your Template

Before installing, validate the YAML structure:

```bash
/mkn-templates:validate-template
```

## Template Structure

### Agent YAML

Agents orchestrate workflow execution:

```yaml
agent:
  name: my-agent
  title: My Agent
  description: What this agent does
  context:
    status: "active"
  workflows:
    - name: main-workflow
      inputs:
        message: $.get('messages', [])
      outputs:
        response: $.get('response')
```

### Workflow YAML

Workflows define task sequences:

```yaml
workflow:
  name: main-workflow
  title: Main Workflow
  outputs:
    response: $.get('result')
    workflow-status: "'executed'"
  tasks:
    - type: prompt
      name: generate-response
      connector:
        name: machina-ai
        command: invoke_prompt
        model: gpt-4o
      outputs:
        result: $.get('response')
```

## Available Skills

| Skill | Description |
|-------|-------------|
| `/mkn-templates:create-template` | Scaffold new template |
| `/mkn-templates:validate-template` | Validate YAML structure |
| `/mkn-templates:install-template` | Install via MCP |

## Documentation

- [Template YAML Reference](template-yaml-reference.md) - Complete YAML syntax
- [Connectors Catalog](connectors-catalog.md) - Available connectors

## Examples

Browse the `agent-templates/` directory for working examples:

- `chat-completion` - Basic chat agent
- `machina-assistant` - Full-featured assistant with RAG
- `coverage-tools` - Sports content generation

## Next Steps

1. Read the [Template YAML Reference](template-yaml-reference.md)
2. Explore existing templates in `agent-templates/`
3. Create your first template with `/mkn-templates:create-template`
