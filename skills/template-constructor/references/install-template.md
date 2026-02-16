---
description: Install Machina templates from local filesystem or Git repositories
---

# DevOps: Install Template

Install Machina templates from local filesystem or Git repositories.

## Trigger

- `/mkn-devops:install-template`
- "Install template [path]"
- "Import template from git"

## Process

### 1. Identify Template Source

Ask user for:
- **Local path**: `/Users/fernando/machina/dazn-templates/agent-templates/moderator-assistant`
- **Git URL**: `https://github.com/machina-sports/dazn-templates` + branch + template path

### 2. Read Installation Manifest

Read the `_install.yml` file to understand:
- Template metadata (title, description, version)
- Required datasets and installation order
- Dependencies (connectors, prompts, etc.)

```yaml
# Example _install.yml structure
setup:
  title: Template Name
  description: What it does
  integrations:
    - google-genai      # Required connectors
    - machina-ai
  version: 1.0.0

datasets:
  - type: connector
    path: scripts/custom.yml
  - type: prompts
    path: prompts/reasoning.yml
  - type: workflow
    path: workflows/main.yml
  - type: agent
    path: agents/executor.yml
```

### 3. Check Prerequisites

Before installing, verify:
1. **Required connectors exist** in target environment
2. **Secrets are configured** for integrations

```python
# Check if connector exists
mcp__docker_localhost__connector_search({
    "filters": {"name": "google-genai"},
    "page": 1,
    "page_size": 1
})

# Check secrets
mcp__docker_localhost__check_secrets({
    "name": "GOOGLE_GENAI_API_KEY"
})
```

### 4. Install Template

#### From Local Filesystem

```python
mcp__docker_localhost__get_local_template({
    "template": "agent-templates/moderator-assistant",
    "project_path": "/app/dazn-templates/agent-templates/moderator-assistant"
})
```

**Note**: `project_path` must be the path **inside the Docker container** (usually `/app/repo-name/...`).

#### From Git Repository

```python
mcp__docker_localhost__import_templates_from_git({
    "repositories": [{
        "repo_url": "https://github.com/machina-sports/dazn-templates",
        "template": "agent-templates/moderator-assistant",
        "repo_branch": "main"
    }]
})
```

### 5. Verify Installation

After importing, verify components were created:

```python
# Check agent exists
mcp__docker_localhost__search_agents({
    "filters": {"name": "moderator-chat-executor"},
    "sorters": ["created", -1],
    "page": 1,
    "page_size": 1
})

# Check workflows exist
mcp__docker_localhost__search_workflow({
    "filters": {"name": "moderator-chat-reasoning"},
    "sorters": ["created", -1],
    "page": 1,
    "page_size": 1
})
```

## MCP Server Selection

Choose the appropriate MCP server based on environment:

| Environment | MCP Server |
|-------------|------------|
| Local dev | `docker_localhost` |
| DAZN Dev | `dazn_moderator_dev` |
| Sportingbet Dev | `sportingbet_blog_dev` |
| Sportingbet Prod | `sportingbet_blog_prd` |

## Example Interaction

```
User: Install the instructions-assistant template from dazn-templates

Claude: I'll install the instructions-assistant template. Let me:

1. Read the _install.yml to understand dependencies
2. Check required connectors (google-genai, machina-ai)
3. Import the template

[Reads _install.yml]

Template: Instructions Assistant
- 1 agent: instructions-chat-executor
- 5 workflows
- 2 prompts
- 1 mapping

[Checks connectors - all present]

[Imports template via MCP]

Installation complete:
- Agent: instructions-chat-executor (created)
- Workflows: 5 created
- Prompts: 2 created

Ready to use. Execute with:
mcp__docker_localhost__execute_agent({
    "agent_id": "<agent_id>",
    "messages": [{"role": "user", "content": "Hello"}],
    "context": {}
})
```

## Common Issues

### "Connector not found"

The template requires a connector that doesn't exist. Install the connector first:

```python
mcp__docker_localhost__get_local_template({
    "template": "connectors/google-genai",
    "project_path": "/app/machina-templates/connectors/google-genai"
})
```

### "Secret not configured"

The connector needs credentials. Create the secret:

```python
mcp__docker_localhost__create_secrets({
    "data": {
        "name": "GOOGLE_GENAI_API_KEY",
        "key": "your-api-key-here"
    }
})
```

### Import succeeds but agent not found

The template path might be wrong. Verify with:

```bash
ls /Users/fernando/machina/dazn-templates/agent-templates/
```

## Related

- [Template YAML Reference](../.claude/guides/template-yaml-reference.md) - YAML structure documentation
- [Connectors Catalog](../.claude/guides/connectors-catalog.md) - Available connectors
