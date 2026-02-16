---
name: template-constructor
description: Construct and scaffold Machina agent-templates and connectors with correct YAML structure, then install them via MCP. Use when users ask to "create a template", "scaffold an agent", "init template", "build a new connector", "install template", "validate template", "analyze template", "trace agent", or "configure secrets". Combines template creation, validation, installation, analysis, tracing, and secret configuration into a single skill.
---

# Template Constructor

End-to-end skill for building, validating, and deploying Machina templates. Covers the full lifecycle: scaffold -> validate -> install -> analyze -> trace -> configure secrets.

## Available Commands

| Command | Description | Reference |
|---------|-------------|-----------|
| `init-template` | Scaffold new template project from scratch | [init-template.md](references/init-template.md) |
| `create-template` | Generate individual YAML components (agent, workflow, prompt, mapping) | [create-template.md](references/create-template.md) |
| `validate-template` | Check YAML files against correct patterns before installation | [validate-template.md](references/validate-template.md) |
| `install-template` | Import templates via MCP (local or Git) | [install-template.md](references/install-template.md) |
| `analyze-template` | Analyze template structure, dependencies, secrets | [analyze-template.md](references/analyze-template.md) |
| `trace-agent` | Trace agent execution chain with variable propagation | [trace-agent.md](references/trace-agent.md) |
| `configure-secrets` | Configure vault secrets for connectors | [configure-secrets.md](references/configure-secrets.md) |

## Quick Workflow

```
1. init-template    → Scaffold project structure
2. create-template  → Add YAML components
3. validate-template → Check syntax before deploy
4. install-template  → Deploy via MCP
5. configure-secrets → Set up credentials
6. analyze-template  → Verify installation
7. trace-agent       → Debug execution flow
```

## Command Dispatch

When the user triggers this skill, determine which command they need:

| User Says | Command |
|-----------|---------|
| "init template", "scaffold template", "new template project" | Read [init-template.md](references/init-template.md) |
| "create agent", "create workflow", "scaffold YAML" | Read [create-template.md](references/create-template.md) |
| "validate", "check YAML", "verify template" | Read [validate-template.md](references/validate-template.md) |
| "install", "import", "deploy template" | Read [install-template.md](references/install-template.md) |
| "analyze", "what's in this template", "overview" | Read [analyze-template.md](references/analyze-template.md) |
| "trace", "execution chain", "variable flow", "debug agent" | Read [trace-agent.md](references/trace-agent.md) |
| "secrets", "credentials", "configure API key" | Read [configure-secrets.md](references/configure-secrets.md) |

Load the appropriate reference file based on the user's intent, then follow its instructions.

## MCP Server Selection

Choose the MCP server based on target environment:

| Environment | MCP Server Prefix |
|-------------|-------------------|
| Local dev | `mcp__docker-localhost__` |
| DAZN Dev | `mcp__dazn-ros-dev__` |
| DAZN Staging | `mcp__dazn-ros-stg__` |
| SBot Dev | `mcp__sbot-dev__` |
| SBot Staging | `mcp__sbot-stg__` |
| SBot Prod | `mcp__sbot-prd__` |
| SIA Dev | `mcp__sia-dev__` |
| Mister AI Dev | `mcp__mister-ai-dev__` |

## SDK Skill Registration

After installing a template, optionally register it as a **skill** in the SDK for discoverability:

```python
mcp__docker-localhost__create_skill(
    name="template-name",
    config={
        "title": "Template Title",
        "description": "What it does",
        "version": "1.0.0",
        "template_path": "agent-templates/template-name",
        "agents": ["template-name-executor"],
        "workflows": ["template-name-main-workflow"],
        "connectors": ["machina-ai"],
        "secrets": ["TEMP_CONTEXT_VARIABLE_SDK_OPENAI_API_KEY"]
    }
)
```

## Template Repository Paths

| Repository | Local Path | Docker Path |
|------------|------------|-------------|
| machina-templates | `/Users/fernando/machina/machina-templates` | `/app/machina-templates` |
| dazn-templates | `/Users/fernando/machina/dazn-templates` | `/app/dazn-templates` |
| entain-templates | `/Users/fernando/machina/entain-templates` | `/app/entain-templates` |

## Key Constraints

- **Connector .py files**: No helper functions outside command functions. Each function must be self-contained.
- **Expression syntax**: Always use `$.get('field')` — never `${field}` or `$field`
- **Prompt files**: Use `prompts:` array (not `prompt:`) with `instruction:` (not `messages:`)
- **Connector YAML**: Use `filetype:` (not `type:`) and `filename:` (not `script:`)
- **Install order**: connectors -> prompts -> mappings -> workflows -> agents
