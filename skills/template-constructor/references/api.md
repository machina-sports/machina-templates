# API

MCP operations for all Machina entities. Covers CRUD, execution, search, and template import.

## Environment Selection

Each environment has its own MCP server prefix. Replace `{mcp}` in examples with the appropriate prefix.

| Environment | Prefix |
|-------------|--------|
| Local dev | `mcp__docker-localhost__` |

Additional environments (dev, staging, production) depend on the project's MCP configuration. Each project may expose multiple server prefixes following the pattern `mcp__{project}-{env}__`.

## Common Patterns

### Search Interface

All `search_*` operations share the same parameters:

| Parameter | Type | Description |
|-----------|------|-------------|
| `filters` | object | MongoDB-style query: `{"name": "value"}`, `{"metadata.key": "value"}` |
| `sorters` | array | `["field", -1]` (desc) or `["field", 1]` (asc). Multi-field: `[["date", -1], ["name", 1]]` |
| `page` | int | Page number (1-indexed) |
| `page_size` | int | Results per page |
| `fields` | array | Field projection: `["name", "title", "status"]` |

### Get by ID or Name

Most `get_*` and `update_*` operations accept either:
- `item_id` — internal ID
- `name` — entity name (string match)

### Execution Queries

Execution search adds:

| Parameter | Type | Description |
|-----------|------|-------------|
| `expanded` | bool | `false` = compact summary, `true` = full task details |
| `totals` | bool | Include aggregate stats (count, tokens, duration) |

---

## Agent

Schema: [agent.md](../schemas/agent.md)

### search_agents

```python
{mcp}search_agents(
    filters={"name": "my-agent"},
    sorters=["name", 1],
    page=1,
    page_size=10,
    fields=["name", "title", "status"]
)
```

### get_agent / get_agent_by_name

```python
{mcp}get_agent(item_id="abc123")
{mcp}get_agent_by_name(name="my-agent")
```

### create_agent

```python
{mcp}create_agent(name="my-agent", config={
    "title": "My Agent",
    "status": "active",
    "config-frequency": 60,
    "context-agent": {"sport": "soccer"},
    "workflows": [...]
})
```

### update_agent

```python
{mcp}update_agent(item_id="abc123", data={"status": "inactive"})
{mcp}update_agent(name="my-agent", data={"config-frequency": 120})
```

### delete_agent

```python
{mcp}delete_agent(item_id="abc123")
```

### execute_agent

Async execution. Returns `agent_run_id` immediately.

```python
{mcp}execute_agent(
    agent_id="abc123",        # or name="my-agent"
    messages=[{"role": "user", "content": "Hello"}],
    context={"context-agent": {"sport": "soccer"}}
)
# Returns: {"agent_run_id": "run_xyz"}
```

### search_agent_executions

```python
{mcp}search_agent_executions(
    filters={"name": "my-agent"},
    sorters=["date", -1],
    page=1,
    page_size=5,
    expanded=False,
    totals=True
)
```

### get_agent_execution

```python
{mcp}get_agent_execution(
    agent_id="run_xyz",    # the execution/run ID
    compact=False          # False = full details with workflows
)
```

---

## Connector

Schema: [connector.md](../schemas/connector.md)

### connector_search

```python
{mcp}connector_search(
    filters={"name": "openai"},
    sorters=["name", 1],
    page=1,
    page_size=10,
    fields=["name", "description", "commands"]
)
```

### connector_retrieve_id / connector_retrieve_args

```python
{mcp}connector_retrieve_id(item_id="abc123")
{mcp}connector_retrieve_args(name="openai")
```

### connector_describe

Returns connector definition with commands and metadata.

```python
{mcp}connector_describe(item_id="abc123")
```

### create_connector

```python
{mcp}create_connector(name="my-connector", config={
    "filename": "my-connector.py",
    "filetype": "pyscript",
    "commands": [{"name": "Do Something", "value": "do_something"}]
})
```

### connector_update

```python
{mcp}connector_update(item_id="abc123", data={...})
```

### delete_connector

```python
{mcp}delete_connector(item_id="abc123")
```

### connector_executor

Execute a connector command directly.

```python
{mcp}connector_executor(item_id="abc123", data={
    "command": "invoke_prompt",
    "inputs": {"api_key": "...", "messages": [...]}
})
```

### connector_endpoint

Call a REST API connector endpoint.

```python
{mcp}connector_endpoint(item_id="abc123", data={
    "endpoint": "/v1/chat/completions",
    "method": "POST",
    "body": {...}
})
```

---

## Document

Schema: [document.md](../schemas/document.md)

### search_documents

```python
{mcp}search_documents(
    filters={"document_name": "sport:Event", "metadata.league": "premier-league"},
    sorters=["date", -1],
    page=1,
    page_size=20,
    document_id="optional-specific-id",
    fields=["title", "content", "metadata"]
)
```

### get_document

```python
{mcp}get_document(
    item_id="abc123",
    fields=["title", "content", "metadata"]
)
```

### create_document

```python
{mcp}create_document(
    name="sport:Event",
    content={"title": "Match A vs B", "data": {...}},
    metadata={"league": "premier-league", "sport": "soccer"}
)
```

### update_document

```python
{mcp}update_document(item_id="abc123", data={
    "content": {"updated": True},
    "metadata": {"status": "processed"}
})
```

### delete_document

```python
{mcp}delete_document(item_id="abc123")
```

### bulk_delete_documents

```python
{mcp}bulk_delete_documents(
    filters={"document_name": "sport:Event", "metadata.status": "expired"},
    batch_size=100
)
```

---

## Mapping

Schema: [mapping.md](../schemas/mapping.md)

### mapping_search

```python
{mcp}mapping_search(
    filters={"name": "my-mapping"},
    sorters=["name", 1],
    page=1,
    page_size=10
)
```

### retrieve_mapping_id / retrieve_mapping_args

```python
{mcp}retrieve_mapping_id(item_id="abc123")
{mcp}retrieve_mapping_args(name="my-mapping")
```

### create_mapping

```python
{mcp}create_mapping(name="my-mapping", config={
    "output": [{"field": "...", "value": "..."}]
})
```

### update_mapping

```python
{mcp}update_mapping(item_id="abc123", data={...})
{mcp}update_mapping(name="my-mapping", data={...})
```

### delete_mapping

```python
{mcp}delete_mapping(item_id="abc123")
```

---

## Prompt

Schema: [prompt.md](../schemas/prompt.md)

### search_prompts

```python
{mcp}search_prompts(
    filters={"name": "my-prompt"},
    sorters=["name", 1],
    page=1,
    page_size=10
)
```

### get_prompt_by_id / get_prompt_by_name

```python
{mcp}get_prompt_by_id(item_id="abc123")
{mcp}get_prompt_by_name(name="my-prompt")
```

### create_prompt

```python
{mcp}create_prompt(name="my-prompt", config={
    "prompts": [{"instruction": "..."}],
    "schema": {...}
})
```

### update_prompt

```python
{mcp}update_prompt(item_id="abc123", data={...})
{mcp}update_prompt(name="my-prompt", data={...})
```

### delete_prompt

```python
{mcp}delete_prompt(item_id="abc123")
```

### execute_prompt

```python
{mcp}execute_prompt(
    prompt_id="abc123",    # or name="my-prompt"
    context={"field": "value"}
)
```

---

## Secrets

Reference: [secrets.md](./secrets.md)

### create_secrets

One secret at a time. Name must follow `TEMP_CONTEXT_VARIABLE_*` pattern.

```python
{mcp}create_secrets(
    name="TEMP_CONTEXT_VARIABLE_OPENAI_API_KEY",
    key="sk-..."
)
```

### check_secrets

```python
{mcp}check_secrets(name="TEMP_CONTEXT_VARIABLE_OPENAI_API_KEY")
# Returns: {"status": "success", "message": "Secret ... exists."}
```

### delete_secrets

```python
{mcp}delete_secrets(name="TEMP_CONTEXT_VARIABLE_OPENAI_API_KEY")
```

---

## Skill

Schema: [skill.md](../schemas/skill.md)

Skills have no dedicated CRUD operations. They are managed through the template import system.

### Install

Skills are defined in `skill.yml` and listed in `_install.yml` with `type: skill`. They are imported alongside other template components:

```python
# Local import (includes skills defined in _install.yml)
{mcp}import_template_from_local(
    template="skills/my-skill",
    project_path="/app/{repo-name}/skills/my-skill"
)

# Git import
{mcp}import_template_from_git(repositories=[{
    "repo_url": "https://github.com/org/repo",
    "template": "skills/my-skill",
    "branch": "main"
}])
```

### Verify

After import, skill references are stored as documents. Search by skill metadata:

```python
{mcp}search_documents(
    filters={"metadata.skill": "my-skill", "metadata.category": "reference"},
    page=1,
    page_size=10
)
```

---

## System

### health_check

```python
{mcp}health_check()
```

---

## Template Import

Reference: [install.md](./install.md)

### import_template_from_local

Import from Docker volume mount.

```python
{mcp}import_template_from_local(
    template="connectors/openai",
    project_path="/app/{repo-name}/connectors/openai"
)
```

`project_path` must point to the Docker-mounted volume path (e.g., `/app/{repo-name}/...`).

### import_template_from_git

Import from Git repository.

```python
{mcp}import_template_from_git(repositories=[
    {
        "repo_url": "https://github.com/org/repo",
        "template": "connectors/openai",
        "branch": "main"
    }
])
```

### import_dataset_direct

Import raw datasets directly.

```python
{mcp}import_dataset_direct(templates=[
    {"name": "doc-name", "type": "document", "content": {...}}
])
```

### get_template_directories

List available templates in a local path.

```python
{mcp}get_template_directories(repo_url="/app/{repo-name}")
```

### get_git_template_directories

List available templates in a Git repository.

```python
{mcp}get_git_template_directories(
    repo_url="https://github.com/org/repo",
    branch="main"
)
```

---

## Workflow

Schema: [workflow.md](../schemas/workflow.md)

### search_workflows

```python
{mcp}search_workflows(
    filters={"name": "my-workflow"},
    sorters=["name", 1],
    page=1,
    page_size=10
)
```

### get_workflow

```python
{mcp}get_workflow(item_id="abc123")
{mcp}get_workflow(name="my-workflow")
```

### create_workflow

```python
{mcp}create_workflow(name="my-workflow", config={
    "tasks": [...],
    "context-variables": {...}
})
```

### update_workflow

```python
{mcp}update_workflow(item_id="abc123", data={"tasks": [...]})
{mcp}update_workflow(name="my-workflow", data={...})
```

### delete_workflow

```python
{mcp}delete_workflow(item_id="abc123")
```

### execute_workflow

Synchronous execution. Returns result when complete.

```python
{mcp}execute_workflow(
    workflow_id="abc123",    # or name="my-workflow"
    context={"key": "value"}
)

# Resume a specific run:
{mcp}execute_workflow(run_id="run_xyz")
```

### schedule_workflow

```python
{mcp}schedule_workflow(
    workflow_id="abc123",    # or name="my-workflow"
    schedule={
        "type": "cron",
        "expression": "0 */6 * * *",
        "enabled": True
    }
)
```

### search_workflow_executions

```python
{mcp}search_workflow_executions(
    filters={"name": "my-workflow"},
    sorters=["date", -1],
    page=1,
    page_size=5,
    expanded=False,
    totals=True
)
```

### get_workflow_execution

```python
{mcp}get_workflow_execution(
    workflow_id="run_xyz",   # the execution/run ID
    compact=False,
    fields=["name", "status", "execution_time", "tasks"]
)
```

---

## Operation Matrix

| Entity | search | get | create | update | delete | execute | schedule |
|--------|--------|-----|--------|--------|--------|---------|----------|
| Agent | `search_agents` | `get_agent` | `create_agent` | `update_agent` | `delete_agent` | `execute_agent` | — |
| Connector | `connector_search` | `connector_retrieve_id` | `create_connector` | `connector_update` | `delete_connector` | `connector_executor` | — |
| Document | `search_documents` | `get_document` | `create_document` | `update_document` | `delete_document` | — | — |
| Mapping | `mapping_search` | `retrieve_mapping_id` | `create_mapping` | `update_mapping` | `delete_mapping` | — | — |
| Prompt | `search_prompts` | `get_prompt_by_id` | `create_prompt` | `update_prompt` | `delete_prompt` | `execute_prompt` | — |
| Secrets | — | `check_secrets` | `create_secrets` | — | `delete_secrets` | — | — |
| Skill | — | — | — | — | — | — | — |
| Workflow | `search_workflows` | `get_workflow` | `create_workflow` | `update_workflow` | `delete_workflow` | `execute_workflow` | `schedule_workflow` |

Skills are managed via Template Import (`import_template_from_local`, `import_template_from_git`).

## Related

- [Install](./install.md) — Template import procedures
- [Secrets](./secrets.md) — Vault configuration
- [Trace](./trace.md) — Execution tracing (uses execution APIs)
- [Analyze](./analyze.md) — Template analysis
