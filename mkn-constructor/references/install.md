# Install

Install Machina templates from local filesystem or Git repositories.

## Trigger

- "Install template", "Import template from git"

## Process

### 1. Identify Template Source

Ask user for:
- **Local path**: `{repo}/agent-templates/{template-name}`
- **Git URL**: repository URL + branch + template path

### 2. Read Installation Manifest

Read `_install.yml` to understand template metadata, required datasets, and dependencies. See [setup.md](../schemas/setup.md) for the complete `_install.yml` schema.

Key things to check:
- Template title, description, version
- Required integrations (connectors)
- Dataset list and installation order

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
{mcp}import_template_from_local(
    template="agent-templates/{template-name}",
    project_path="/app/{repo-name}/agent-templates/{template-name}"
)
```

**Note**: `project_path` must be the path **inside the Docker container** (usually `/app/{repo-name}/...`).

#### From Git Repository

```python
{mcp}import_template_from_git(repositories=[{
    "repo_url": "https://github.com/org/repo",
    "template": "agent-templates/{template-name}",
    "branch": "main"
}])
```

### 5. Verify Installation

After importing, verify components were created:

```python
# Check agent exists
{mcp}search_agents(
    filters={"name": "my-agent"},
    sorters=["created", -1],
    page=1,
    page_size=1
)

# Check workflows exist
{mcp}search_workflows(
    filters={"name": "my-workflow"},
    sorters=["created", -1],
    page=1,
    page_size=1
)
```

See [api.md](./api.md) for the full MCP operations reference.

## MCP Server Selection

| Environment | MCP Server Prefix |
|-------------|-------------------|
| Local dev | `mcp__docker-localhost__` |

Additional environments depend on the project's MCP configuration. Pattern: `mcp__{project}-{env}__`.

## Common Issues

### "Connector not found"

Install the connector first:

```python
mcp__docker_localhost__get_local_template({
    "template": "connectors/google-genai",
    "project_path": "/app/machina-templates/connectors/google-genai"
})
```

### "Secret not configured"

Create the secret — see [Secrets](./secrets.md) for the full process:

```python
mcp__docker_localhost__create_secrets({
    "data": {
        "name": "GOOGLE_GENAI_API_KEY",
        "key": "your-api-key-here"
    }
})
```

### Import succeeds but agent not found

The template path might be wrong. Verify the local path exists before importing.

## Related

- [Validate](./validate.md) — Validate YAML before installing
- [Secrets](./secrets.md) — Configure credentials
- [Analyze](./analyze.md) — Verify installation
