---
description: Analyze agent-template structure and provide overview of agents, workflows, prompts, and dependencies
---

# DevOps: Analyze Template

Analyze a Machina agent-template and provide a comprehensive overview of its components.

## Trigger

- `/mkn-devops:analyze-template`
- "Analyze template [path]"
- "What's in this template?"
- "Overview of template"

## Process

### 1. Identify Template Path

Ask user for the template location if not provided:
- Local: `/Users/fernando/machina/dazn-templates/agent-templates/moderator-assistant`
- Or template name to search in known repos

**Known template repositories:**
- `/Users/fernando/machina/dazn-templates/agent-templates/`
- `/Users/fernando/machina/entain-templates/agent-templates/`
- `/Users/fernando/machina/machina-templates/agent-templates/`

### 2. Discover All Files

List all YAML files in the template directory:
```bash
find <template-path> -type f -name "*.yml" | sort
```

Note special structures:
- `agents/` - Agent definitions
- `workflows/` - Workflow definitions
- `prompts/` - Prompt definitions
- `mappings/` - Data mappings
- `scripts/` - Connector definitions (.yml + .py)
- `configs/` - Setup/configuration workflows
- `custom-*/` - Custom subdirectories (polls, quizzes, game, etc.)
- `documents/` - Static document templates

### 3. Read Installation Manifest

Read `_install.yml` to extract:

| Field | Location | Purpose |
|-------|----------|---------|
| title | `setup.title` | Template display name |
| description | `setup.description` | What it does |
| version | `setup.version` | Semantic version |
| category | `setup.category` | Classification (special-templates, connectors, etc.) |
| estimatedTime | `setup.estimatedTime` | Installation time |
| features | `setup.features` | Feature bullet list |
| integrations | `setup.integrations` | Required connectors |
| status | `setup.status` | available, beta, deprecated |
| datasets | `datasets[]` | Installation order and types |

### 4. Analyze Components

#### Agents (`agents/*.yml`)

For each agent, extract:

| Property | YAML Path | Notes |
|----------|-----------|-------|
| Name | `agent.name` | Unique identifier |
| Title | `agent.title` | Display name |
| Description | `agent.description` | Purpose |
| Type | - | LLM-based or Orchestrator (has `workflows:`) |
| Model | `agent.model` or from connector | google-genai, machina-ai, etc. |
| System Prompt | `agent.system-prompt` | Reference to prompt name |
| Tools | `agent.tools[]` | Connectors used |
| Config | `agent.context.config-*` | frequency, temperature, etc. |
| Status | `agent.context.status` | active, inactive |
| context-agent | `agent.context-agent` | Input parameters with defaults |
| Workflows | `agent.workflows[]` | For orchestrator agents |

**Agent Types:**
- **LLM-based**: Has `model`, `system-prompt`, `tools`
- **Orchestrator**: Has `workflows[]` list, coordinates multiple workflows

#### Workflows (`workflows/*.yml`, `configs/*.yml`, `custom-*/*.yml`)

For each workflow, extract:

| Property | YAML Path | Notes |
|----------|-----------|-------|
| Name | `workflow.name` | Unique identifier |
| Title | `workflow.title` | Display name |
| Description | `workflow.description` | Purpose |
| Inputs | `workflow.inputs` | Input parameters |
| Outputs | `workflow.outputs` | Return values |
| Context Variables | `workflow.context-variables` | API keys, debugger, etc. |
| Tasks | `workflow.tasks[]` | Execution steps |

**Task Types:**
| Type | Purpose | Key Fields |
|------|---------|------------|
| `document` | CRUD on documents | `action`, `filters`, `documents` |
| `connector` | Call external service | `connector.name`, `connector.command` |
| `prompt` | LLM generation | `connector`, `inputs`, schema |
| `mapping` | Data transformation | `inputs`, `outputs` |
| `function` | Inline Python code | `code` |
| `agent` | Execute sub-agent | `agent.name` |

**Special Patterns:**
- `foreach` - Loop over array: `foreach.value`, `foreach.name`, `foreach.expr`
- `condition` - Conditional execution: Python expression
- `config.action` - document actions: search, save, update, bulk-save, delete

**Credentials Extraction:**

Look for `context-variables` with values starting with `$`:
```yaml
context-variables:
  google-genai:
    api_key: "$TEMP_CONTEXT_VARIABLE_GOOGLE_GENERATIVE_AI_API_KEY"
  machina-ai:
    api_key: "$TEMP_CONTEXT_VARIABLE_SDK_OPENAI_API_KEY"
```

Extract and deduplicate all `$VARIABLE_NAME` references across workflows to build the Required Credentials list.

#### Prompts (`prompts/*.yml`, `custom-*/prompts.yml`)

For each prompt, extract:

| Property | YAML Path | Notes |
|----------|-----------|-------|
| Name | `prompts[].name` | Unique identifier |
| Title | `prompts[].title` | Display name |
| Description | `prompts[].description` | Purpose |
| Instruction | `prompts[].instruction` | System instruction text |
| Schema | `prompts[].schema` | JSON Schema for structured output |
| Languages | Schema properties | title_es, title_it, title_de, etc. |

**Language Support:** Check for `title_es`, `title_it`, `title_de`, `title_fr`, `title_pt`, `title_ja`, `title_he`, `title_ar` in schema.

#### Mappings (`mappings/*.yml`)

For each mapping, extract:
- **Name** and **Description**
- **Inputs** - Source data
- **Outputs** - Transformed data
- **Logic** - Transformation expressions

#### Connectors (`scripts/*.yml`)

For each connector defined in the template, extract:

| Property | YAML Path | Notes |
|----------|-----------|-------|
| Name | `connector.name` | Unique identifier |
| Title | `connector.title` | Display name |
| Description | `connector.description` | Purpose |
| Type | `connector.filetype` | pyscript, api, etc. |
| Filename | `connector.filename` | Python file (.py) |
| Status | `connector.status` | active, inactive |
| Commands | `connector.commands[]` | Available functions |

#### Connector Usage Discovery

Scan all workflows for connector references:
```bash
grep -r "connector:" -A 3 <template-path> --include="*.yml" | grep -E "(name:|command:)"
```

Extract unique connectors and their commands:
- Connector name from `connector.name`
- Command from `connector.command`
- Workflow file where it's used

#### Connector-to-Secrets Mapping

Cross-reference discovered connectors with actual secret variable names used in the platform:

| Connector | Secret Variable | Description |
|-----------|-----------------|-------------|
| `google-genai` | `$TEMP_CONTEXT_VARIABLE_GOOGLE_GENERATIVE_AI_API_KEY` | Google Generative AI API Key |
| `machina-ai` | `$TEMP_CONTEXT_VARIABLE_SDK_OPENAI_API_KEY` | Machina AI / OpenAI API Key |
| `google-storage` | `$MACHINA_CONTEXT_VARIABLE_GOOGLE_STORAGE_API_KEY` | GCS Service Account JSON |
| `google-storage` | `$MACHINA_CONTEXT_VARIABLE_GOOGLE_STORAGE_BUCKET_NAME` | GCS Bucket Name |
| `sportradar-soccer` | `$TEMP_CONTEXT_VARIABLE_SPORTRADAR_SOCCER_V4_API_KEY` | SportRadar Soccer API Key |
| `sportradar-nba` | `$TEMP_CONTEXT_VARIABLE_SPORTRADAR_NBA_API_KEY` | SportRadar NBA API Key |
| `sportradar-nfl` | `$TEMP_CONTEXT_VARIABLE_SPORTRADAR_NFL_API_KEY` | SportRadar NFL API Key |
| `openai` | `$TEMP_CONTEXT_VARIABLE_OPENAI_API_KEY` | OpenAI API Key |
| `groq` | `$TEMP_CONTEXT_VARIABLE_GROQ_API_KEY` | Groq API Key |
| `wordpress` | `$TEMP_CONTEXT_VARIABLE_WORDPRESS_BEARER_TOKEN` | WordPress Bearer Token |
| `api-football` | `$TEMP_CONTEXT_VARIABLE_API_FOOTBALL_API_KEY` | API-Football Key |
| `bwin` | `$TEMP_CONTEXT_VARIABLE_BWIN_ACCESS_ID` | BWin Access ID |
| `bwin` | `$TEMP_CONTEXT_VARIABLE_BWIN_ACCESS_ID_TOKEN` | BWin Access Token |
| `vertex-ai` | `$TEMP_CONTEXT_VARIABLE_VERTEX_AI_CREDENTIAL` | Vertex AI Service Account |
| `vertex-ai` | `$TEMP_CONTEXT_VARIABLE_VERTEX_AI_PROJECT_ID` | Vertex AI Project ID |
| `temp-downloader` | None | Public URL access only |
| `storage` | None | Local storage |

**Note**: Secret names follow the pattern `$TEMP_CONTEXT_VARIABLE_<SERVICE>_<KEY_TYPE>`

**Reference**: See [Connectors Catalog](/.claude/guides/connectors-catalog.md) for complete list

### 5. Generate Report

Use this template structure:

```markdown
# Template Analysis: {template-name}

## Overview
| Field | Value |
|-------|-------|
| **Title** | {from _install.yml} |
| **Description** | {description} |
| **Version** | {version} |
| **Category** | {category} |
| **Estimated Time** | {estimatedTime} |

## Features
- Feature 1
- Feature 2
- ...

## Dependencies

### Required Connectors
| Connector | Purpose |
|-----------|---------|
| connector-1 | Description |
| connector-2 | Description |

### External Dependencies
- GCS bucket: {url}
- External API: {name}

### Required Secrets
| Secret | Purpose |
|--------|---------|
| SECRET_NAME | What it's used for |

### Required Credentials (from context-variables)
| Variable | Connector | Workflow |
|----------|-----------|----------|
| `$TEMP_CONTEXT_VARIABLE_GOOGLE_GENERATIVE_AI_API_KEY` | google-genai | workflow-name |
| `$TEMP_CONTEXT_VARIABLE_SDK_OPENAI_API_KEY` | machina-ai | workflow-name |

### Connectors Used
| Connector | Commands | Workflows |
|-----------|----------|-----------|
| google-genai | invoke_prompt | custom-* |
| machina-ai | invoke_prompt | custom-* |
| temp-downloader | invoke_download, invoke_read_json | sync-*, ros-engine |
| google-storage | invoke_upload | generate-and-upload |

### Complete Secrets Checklist
| Secret Variable | Connector | Source | Required |
|-----------------|-----------|--------|----------|
| `$TEMP_CONTEXT_VARIABLE_GOOGLE_GENERATIVE_AI_API_KEY` | google-genai | context-variables | Yes |
| `$TEMP_CONTEXT_VARIABLE_SDK_OPENAI_API_KEY` | machina-ai | context-variables | Yes |
| `$MACHINA_CONTEXT_VARIABLE_GOOGLE_STORAGE_API_KEY` | google-storage | connector | Conditional |
| `$MACHINA_CONTEXT_VARIABLE_GOOGLE_STORAGE_BUCKET_NAME` | google-storage | connector | Conditional |

## Components Summary

| Type | Count | Files |
|------|-------|-------|
| Agents | X | file1.yml, file2.yml |
| Workflows | X | file1.yml, ... |
| Prompts | X | file1.yml |
| Mappings | X | file1.yml |
| Connectors | X | file1.yml |

---

## Agents Detail

### {agent-name}
| Property | Value |
|----------|-------|
| **Description** | ... |
| **Type** | LLM-based / Orchestrator |
| **Model** | google-genai (gemini-2.0-flash) |
| **Status** | active / inactive |

**Parameters (context-agent):**
- `param1` - Description (default: value)
- `param2` - Description

**Orchestrated Workflows:** (if orchestrator)
1. workflow-1 - Description
2. workflow-2 - Description (condition: ...)

---

## Workflows Detail

### Core Workflows

#### {workflow-name}
| Property | Value |
|----------|-------|
| **Description** | ... |
| **Inputs** | param1, param2 |
| **Outputs** | output1, output2 |
| **Tasks** | X steps |

**Task Flow:**
```
task-1 (document) → task-2 (connector) → task-3 (document)
```

### Setup Workflows
- workflow-setup-dev - Description
- workflow-setup-prd - Description

### Sync Workflows
- workflow-sync-x - Description

---

## Connector Detail

### {connector-name}
| Property | Value |
|----------|-------|
| **Type** | pyscript |
| **File** | filename.py |
| **Status** | active |

**Commands:**
| Command | Function |
|---------|----------|
| Command Name | function_name |

---

## Prompts Detail

### {prompt-name}
| Property | Value |
|----------|-------|
| **Purpose** | What it generates |
| **Used by** | workflow or agent name |
| **Languages** | EN, ES, IT, DE, FR, PT, JA, HE, AR |
| **Schema** | SchemaName (key fields) |

---

## Data Flow Diagram

```
                    ┌─────────────────────────────────────────┐
                    │           External Source                │
                    └─────────────┬───────────────────────────┘
                                  │
            ┌─────────────────────┼─────────────────────┐
            ▼                     ▼                     ▼
    ┌───────────────┐    ┌───────────────┐    ┌───────────────┐
    │   workflow-1  │    │   workflow-2  │    │   workflow-3  │
    └───────┬───────┘    └───────┬───────┘    └───────┬───────┘
            │                    │                    │
            ▼                    ▼                    ▼
    ┌───────────────┐    ┌───────────────┐    ┌───────────────┐
    │   document-1  │    │   document-2  │    │   document-3  │
    └───────────────┘    └───────────────┘    └───────────────┘
```

---

## Installation Order

From `_install.yml` datasets:
1. type: connector - path
2. type: prompts - path
3. type: workflow - path
4. type: agent - path
```

### 6. Output Options

Ask user preference:
- **Console**: Display report in terminal (default)
- **File**: Save to `{template-name}-analysis.md`

## Example Analysis

See actual analysis of `dazn-runofshow` template for reference format.

## Tips

- Use this skill **before** installing a template to understand its requirements
- Check required connectors are available in target environment
- Verify secrets are configured before installation
- Review agent models to ensure API keys are available
- Look for `foreach` patterns - they indicate batch processing
- Check `condition` fields - they show branching logic
- **Credentials**: Scan all `context-variables` for `$TEMP_CONTEXT_VARIABLE_*` patterns - these must be configured in the environment secrets
- Common credential patterns:
  - `$TEMP_CONTEXT_VARIABLE_GOOGLE_GENERATIVE_AI_API_KEY` → Google AI
  - `$TEMP_CONTEXT_VARIABLE_SDK_OPENAI_API_KEY` → Machina AI / OpenAI
  - `$TEMP_CONTEXT_VARIABLE_SPORTRADAR_API_KEY` → SportRadar
