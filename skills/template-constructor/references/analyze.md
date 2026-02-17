# Analyze

Analyze a Machina template and provide a comprehensive overview of its components, dependencies, and credentials.

## Trigger

- `/mkn-templates:analyze-template`
- "Analyze template", "What's in this template?", "Overview of template"

## Process

### 1. Identify Template Path

Ask user for the template location. Typical structure:
- `{repo}/agent-templates/{template-name}/`
- `{repo}/connectors/{connector-name}/`

### 2. Discover All Files

List all YAML files in the template directory. Note special directories: `agents/`, `workflows/`, `prompts/`, `mappings/`, `scripts/`, `configs/`, `setup/`, `instructions/`, `documents/`.

### 3. Read Installation Manifest

Read `_install.yml` and extract setup metadata. See [setup.md](../schemas/setup.md) for field reference.

### 4. Analyze Components

For each component type, read the relevant schema for field definitions, then extract key information:

| Component | Schema | Extract |
|-----------|--------|---------|
| Agents | [agent.md](../schemas/agent.md) | name, type (LLM vs orchestrator), status, context-agent params, workflow list |
| Workflows | [workflow.md](../schemas/workflow.md) | name, inputs/outputs, context-variables, task list with types |
| Prompts | [prompt.md](../schemas/prompt.md) | name, instruction summary, schema fields, language support |
| Mappings | [mapping.md](../schemas/mapping.md) | name, output transformations |
| Connectors | [connector.md](../schemas/connector.md) | name, type (pyscript/restapi), commands |
| Documents | [setup.md](../schemas/setup.md) Part 2 | document entries, filetypes, metadata |
| Skills | [skill.md](../schemas/skill.md) | name, references, workflow/agent entry points |

#### Credentials Extraction

Scan all `context-variables` for values starting with `$`:

```yaml
context-variables:
  google-genai:
    api_key: "$TEMP_CONTEXT_VARIABLE_GOOGLE_GENERATIVE_AI_API_KEY"
```

Deduplicate all `$VARIABLE_NAME` references to build the Required Credentials list.

#### Connector-to-Secrets Mapping

Cross-reference discovered connectors with known secret patterns:

| Connector | Secret Variable |
|-----------|-----------------|
| `google-genai` | `$TEMP_CONTEXT_VARIABLE_GOOGLE_GENERATIVE_AI_API_KEY` |
| `machina-ai` | `$TEMP_CONTEXT_VARIABLE_SDK_OPENAI_API_KEY` |
| `google-storage` | `$MACHINA_CONTEXT_VARIABLE_GOOGLE_STORAGE_API_KEY` |
| `sportradar-soccer` | `$TEMP_CONTEXT_VARIABLE_SPORTRADAR_SOCCER_V4_API_KEY` |
| `sportradar-nfl` | `$TEMP_CONTEXT_VARIABLE_SPORTRADAR_NFL_API_KEY` |
| `sportradar-nba` | `$TEMP_CONTEXT_VARIABLE_SPORTRADAR_NBA_API_KEY` |
| `openai` | `$TEMP_CONTEXT_VARIABLE_OPENAI_API_KEY` |
| `groq` | `$TEMP_CONTEXT_VARIABLE_GROQ_API_KEY` |
| `bwin` | `$TEMP_CONTEXT_VARIABLE_BWIN_ACCESS_ID` |
| `vertex-ai` | `$TEMP_CONTEXT_VARIABLE_VERTEX_AI_CREDENTIAL` |

### 5. Generate Report

```markdown
# Template Analysis: {template-name}

## Overview
| Field | Value |
|-------|-------|
| **Title** | ... |
| **Description** | ... |
| **Version** | ... |
| **Category** | ... |

## Components Summary
| Type | Count | Files |
|------|-------|-------|
| Agents | X | file1.yml, file2.yml |
| Workflows | X | ... |
| Prompts | X | ... |
| Mappings | X | ... |
| Connectors | X | ... |

## Required Credentials
| Variable | Connector | Workflow |
|----------|-----------|----------|
| `$TEMP_...` | connector-name | workflow-name |

## Connectors Used
| Connector | Commands | Workflows |
|-----------|----------|-----------|
| google-genai | invoke_prompt | ... |

## Agents Detail
### {agent-name}
- Type: Orchestrator
- Status: active
- Workflows: N steps

## Workflows Detail
### {workflow-name}
- Tasks: N steps
- Flow: task-1 → task-2 → task-3

## Data Flow Diagram
(ASCII diagram showing agent → workflows → connectors/documents)

## Installation Order
(from _install.yml datasets)
```

## Tips

- Use this skill **before** installing to understand requirements
- Check required connectors are available in target environment
- Verify secrets are configured before installation
- Look for `foreach` patterns — they indicate batch processing
- Check `condition` fields — they show branching logic

## Related

- [Install](./install.md) — Install analyzed templates
- [Trace](./trace.md) — Trace specific agent execution chains
- [Secrets](./secrets.md) — Configure required credentials
