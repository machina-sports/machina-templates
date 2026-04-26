# Skill YAML Schema

Skills register capabilities in the SDK/Studio for discoverability. They link reference documents and define entry points (workflows or agents) that users can invoke.

**Location**: `skills/<skill-name>/skill.yml` or `agent-templates/<template-name>/skill.yml`

---

## Root Structure

```yaml
skill:
  name: <string>              # Required. Unique identifier (kebab-case)
  title: <string>             # Required. Human-readable title
  description: <string>       # Required. What this skill does
  version: <string>           # Required. Semantic version
  category: <list>            # Required. Classification tags
  status: <string>            # Required. "available" or "draft"
  domain: <string>            # Required. Repository URL

  references: <list>          # Optional. Linked reference documents
  workflows: <list>           # Optional. Workflow entry points
  agents: <list>              # Optional. Agent entry points
```

**Note**: The root key is `skill:` (singular object), not `skills:` (array). Each file defines exactly one skill.

---

## Field Reference

### `name` (required)

Unique identifier. Used for dispatching the skill via the SDK.

```yaml
name: "polymarket-sync-events"
name: "mkn-constructor"
name: "adapters-dataset-generate"
```

### `title` (required)

```yaml
title: "Polymarket - Sync Events"
title: "Template Constructor"
title: "Adapters - Dataset Generate"
```

### `description` (required)

```yaml
description: "Sync sports events from Polymarket to Machina documents."
description: "End-to-end skill for building, validating, and deploying Machina agent-templates and connectors."
description: "Run full dataset pipeline: checkin → generate → annotate → build → checkout. Uses the adapters-dataset-pipeline agent."
```

### `version` (required)

Semantic versioning.

```yaml
version: "1.0.0"
version: "2.0.0"
```

### `category` (required)

Array of classification tags for filtering and grouping in the SDK.

```yaml
category:
  - "data-acquisition"
  - "prediction-markets"

category:
  - "devops"
  - "templates"

category:
  - "dataset"
  - "fine-tuning"

category:
  - "testing"
  - "fine-tuning"

category:
  - "setup"
  - "devops"

category:
  - "guide"
  - "fine-tuning"
```

### `status` (required)

```yaml
status: "available"
status: "draft"
```

### `domain` (required)

URL of the repository that owns this skill. Used for provenance tracking.

```yaml
domain: "https://github.com/machina-sports/machina-templates"
domain: "https://github.com/machina-sports/machina-model-template"
```

---

## References

Array of documents linked to the skill. These are imported as documents and become available to the SDK for context.

```yaml
references:
  - name: <string>            # Required. Document name ("skill-guide", "skill-reference", or "skill-schema")
    title: <string>           # Required. Display title
    filename: <string>        # Required. File path relative to skill directory
    filetype: <string>        # Required. File format
    metadata: <object>        # Required. Categorization metadata
```

### Reference Types

| `name` value | `metadata.category` | Purpose |
|-------------|---------------------|---------|
| `skill-guide` | `"skill-guide"` | Main guide document (typically `SKILL.md`) |
| `skill-reference` | `"reference"` | Supporting reference document |
| `skill-schema` | `"skill-schema"` | YAML field definition / entity schema |

### `metadata` Fields

| Field | Required | Description |
|-------|----------|-------------|
| `category` | Yes | `"skill-guide"`, `"reference"`, or `"skill-schema"` |
| `skill` | Yes | Must match the skill `name` |
| `reference_id` | Only for `skill-reference` and `skill-schema` | Unique ID within the skill |

### Examples

**Skill guide** (main documentation):

```yaml
references:
  - name: "skill-guide"
    title: "Adapters - Guide"
    filename: "SKILL.md"
    filetype: "markdown"
    metadata:
      category: "skill-guide"
      skill: "adapters-guide"
```

**Skill references** (supporting docs):

```yaml
references:
  - name: "skill-reference"
    title: "Events API"
    filename: "references/events-api.md"
    filetype: "markdown"
    metadata:
      category: "reference"
      skill: "polymarket-sync-events"
      reference_id: "events-api"

  - name: "skill-reference"
    title: "Search"
    filename: "references/search.md"
    filetype: "markdown"
    metadata:
      category: "reference"
      skill: "polymarket-sync-events"
      reference_id: "search"
```

**Skill schemas** (YAML entity definitions):

```yaml
references:
  - name: "skill-schema"
    title: "Schema: Agent"
    filename: "schemas/agent.md"
    filetype: "markdown"
    metadata:
      category: "skill-schema"
      skill: "mkn-constructor"
      reference_id: "schema-agent"

  - name: "skill-schema"
    title: "Schema: Workflow"
    filename: "schemas/workflow.md"
    filetype: "markdown"
    metadata:
      category: "skill-schema"
      skill: "mkn-constructor"
      reference_id: "schema-workflow"
```

**Mixed guide + references + schemas**:

```yaml
references:
  - name: "skill-guide"
    title: "Template Constructor"
    filename: "SKILL.md"
    filetype: "markdown"
    metadata:
      category: "skill-guide"
      skill: "mkn-constructor"

  - name: "skill-reference"
    title: "Install"
    filename: "references/install.md"
    filetype: "markdown"
    metadata:
      category: "reference"
      skill: "mkn-constructor"
      reference_id: "install"

  - name: "skill-schema"
    title: "Schema: Agent"
    filename: "schemas/agent.md"
    filetype: "markdown"
    metadata:
      category: "skill-schema"
      skill: "mkn-constructor"
      reference_id: "schema-agent"
```

---

## Entry Points

Skills expose entry points that users can invoke. There are two types: **workflows** (dispatch a single workflow) and **agents** (dispatch an agent that orchestrates multiple workflows). A skill can have one or both, or neither (guide-only skills).

### `workflows` (optional)

Array of workflow entry points. Each dispatches a named workflow.

```yaml
workflows:
  - name: <string>            # Required. Workflow name to dispatch
    description: <string>     # Required. Short description
    inputs: <object>          # Required. Input expressions with defaults
    outputs: <object>         # Required. Output expressions
```

**Example — single workflow**:

```yaml
workflows:
  - name: "polymarket-sync-events"
    description: "sync-sports-events"
    inputs:
      tag_id: "$.get('tag_id', 1)"
      series_id: "$.get('series_id', '')"
      limit: "$.get('limit', 100)"
      offset: "$.get('offset', 0)"
    outputs:
      workflow-status: "$.get('workflow-status', 'skipped')"
```

**Example — multiple workflows**:

```yaml
workflows:
  - name: "adapters-test-report-workflow"
    description: "run-test-report"
    inputs:
      model_key: "$.get('model_key', 'sbot_classifier')"
      adapter_type: "$.get('adapter_type', 'classifier')"
      system_prompt: "$.get('system_prompt', '')"
    outputs:
      workflow-status: "$.get('workflow-status', 'skipped')"

  - name: "adapters-test-workflow"
    description: "test-single-query"
    inputs:
      message: "$.get('message', 'Quais são os jogos do Flamengo hoje?')"
      model_key: "$.get('model_key', 'sbot_classifier')"
      adapter_type: "$.get('adapter_type', 'classifier')"
    outputs:
      workflow-status: "$.get('workflow-status', 'skipped')"
```

### `agents` (optional)

Array of agent entry points. Each dispatches a named agent (which orchestrates multiple workflows).

```yaml
agents:
  - name: <string>            # Required. Agent name to dispatch
    description: <string>     # Required. Short description
    inputs: <object>          # Required. Input expressions with defaults
    outputs: <object>         # Required. Output expressions
```

**Example**:

```yaml
agents:
  - name: "adapters-dataset-pipeline"
    description: "full-dataset-pipeline"
    inputs:
      adapter_type: "$.get('adapter_type', 'classifier')"
      batch_prompts: "$.get('batch_prompts', [])"
      annotate: "$.get('annotate', False)"
      version: "$.get('version', 'v1')"
      n: "$.get('n', 25)"
      val_ratio: "$.get('val_ratio', 0.10)"
      dedup_threshold: "$.get('dedup_threshold', 0.80)"
    outputs:
      workflow-status: "$.get('workflow-status', 'skipped')"
```

### Input/Output Expression Syntax

Inputs and outputs use the same `$.get()` expression syntax as workflows.

```yaml
# Simple with default
tag_id: "$.get('tag_id', 1)"

# String default
series_id: "$.get('series_id', '')"

# Boolean default
annotate: "$.get('annotate', False)"

# List default
batch_prompts: "$.get('batch_prompts', [])"

# Float default
val_ratio: "$.get('val_ratio', 0.10)"

# Standard workflow-status output
workflow-status: "$.get('workflow-status', 'skipped')"
```

---

## Pattern Examples

### Data Acquisition Skill (workflow + references)

```yaml
skill:
  name: "polymarket-sync-markets"
  title: "Polymarket - Sync Markets"
  description: "Sync sports prediction markets from Polymarket to Machina documents."
  version: "1.0.0"
  category:
    - "data-acquisition"
    - "prediction-markets"
  status: "available"
  domain: "https://github.com/machina-sports/machina-templates"

  references:
    - name: "skill-reference"
      title: "Market Types"
      filename: "references/market-types.md"
      filetype: "markdown"
      metadata:
        category: "reference"
        skill: "polymarket-sync-markets"
        reference_id: "market-types"

    - name: "skill-reference"
      title: "Pricing API"
      filename: "references/pricing-api.md"
      filetype: "markdown"
      metadata:
        category: "reference"
        skill: "polymarket-sync-markets"
        reference_id: "pricing-api"

  workflows:
    - name: "polymarket-sync-markets"
      description: "sync-sports-markets"
      inputs:
        tag_id: "$.get('tag_id', 1)"
        sports_market_types: "$.get('sports_market_types', '')"
        limit: "$.get('limit', 100)"
        offset: "$.get('offset', 0)"
      outputs:
        workflow-status: "$.get('workflow-status', 'skipped')"
```

### DevOps Skill (many references, no agents)

```yaml
skill:
  name: "mkn-constructor"
  title: "Template Constructor"
  description: "End-to-end skill for building, validating, and deploying Machina agent-templates and connectors."
  version: "1.0.0"
  category:
    - "devops"
    - "templates"
  status: "available"
  domain: "https://github.com/machina-sports/machina-templates"

  references:
    - name: "skill-reference"
      title: "Init Template"
      filename: "references/init-template.md"
      filetype: "markdown"
      metadata:
        category: "reference"
        skill: "mkn-constructor"
        reference_id: "init-template"

    - name: "skill-reference"
      title: "Create Template"
      filename: "references/create-template.md"
      filetype: "markdown"
      metadata:
        category: "reference"
        skill: "mkn-constructor"
        reference_id: "create-template"

    # ... more references ...

  workflows:
    - name: "mkn-constructor-check-setup"
      description: "check-doc-structure"
      inputs:
        document_name: "$.get('document_name', 'doc-structure')"
      outputs:
        doc-structure: "$.get('doc-structure', {})"
        check-status: "$.get('workflow-status')"
```

### Pipeline Skill (agent entry point)

Uses `agents` instead of `workflows` to dispatch an agent that orchestrates a multi-step pipeline.

```yaml
skill:
  name: "adapters-dataset-pipeline"
  title: "Adapters - Dataset Pipeline"
  description: "Run full dataset pipeline: checkin → generate → annotate → build → checkout."
  version: "1.0.0"
  category:
    - "dataset"
    - "fine-tuning"
  status: "available"
  domain: "https://github.com/machina-sports/machina-model-template"

  references:
    - name: "skill-guide"
      title: "Adapters - Dataset Pipeline"
      filename: "SKILL.md"
      filetype: "markdown"
      metadata:
        category: "skill-guide"
        skill: "adapters-dataset-pipeline"

    - name: "skill-reference"
      title: "Pipeline Flow"
      filename: "references/pipeline-flow.md"
      filetype: "markdown"
      metadata:
        category: "reference"
        skill: "adapters-dataset-pipeline"
        reference_id: "pipeline-flow"

    - name: "skill-reference"
      title: "Adapter Types"
      filename: "references/adapter-types.md"
      filetype: "markdown"
      metadata:
        category: "reference"
        skill: "adapters-dataset-pipeline"
        reference_id: "adapter-types"

  agents:
    - name: "adapters-dataset-pipeline"
      description: "full-dataset-pipeline"
      inputs:
        adapter_type: "$.get('adapter_type', 'classifier')"
        batch_prompts: "$.get('batch_prompts', [])"
        annotate: "$.get('annotate', False)"
        version: "$.get('version', 'v1')"
        n: "$.get('n', 25)"
        val_ratio: "$.get('val_ratio', 0.10)"
        dedup_threshold: "$.get('dedup_threshold', 0.80)"
      outputs:
        workflow-status: "$.get('workflow-status', 'skipped')"
```

### Guide-Only Skill (references only, no entry points)

Documentation skill with no executable entry points.

```yaml
skill:
  name: "adapters-guide"
  title: "Adapters - Guide"
  description: "Guide for creating a new LoRA adapter end-to-end: setup, dataset pipeline, train, deploy, eval."
  version: "1.0.0"
  category:
    - "guide"
    - "fine-tuning"
  status: "available"
  domain: "https://github.com/machina-sports/machina-model-template"

  references:
    - name: "skill-guide"
      title: "Adapters - Guide"
      filename: "SKILL.md"
      filetype: "markdown"
      metadata:
        category: "skill-guide"
        skill: "adapters-guide"
```

### Setup Skill (references only)

```yaml
skill:
  name: "adapters-setup"
  title: "Adapters - Setup"
  description: "Install the machina-model-template and verify all components are properly deployed."
  version: "1.0.0"
  category:
    - "setup"
    - "devops"
  status: "available"
  domain: "https://github.com/machina-sports/machina-model-template"

  references:
    - name: "skill-guide"
      title: "Adapters - Setup"
      filename: "SKILL.md"
      filetype: "markdown"
      metadata:
        category: "skill-guide"
        skill: "adapters-setup"

    - name: "skill-reference"
      title: "Installation Guide"
      filename: "references/installation-guide.md"
      filetype: "markdown"
      metadata:
        category: "reference"
        skill: "adapters-setup"
        reference_id: "installation-guide"

    - name: "skill-reference"
      title: "Component Inventory"
      filename: "references/component-inventory.md"
      filetype: "markdown"
      metadata:
        category: "reference"
        skill: "adapters-setup"
        reference_id: "component-inventory"
```

---

## How Skills Are Installed

Skills are registered in the `_install.yml` manifest as `type: skill`:

```yaml
# In _install.yml
datasets:
  # ... connectors, workflows, agents first ...

  - type: skill
    path: skills/sync-markets/skill.yml
  - type: skill
    path: skills/sync-events/skill.yml
  - type: skill
    path: skills/sync-series/skill.yml
```

**Install order**: Skills come **last** in the datasets array (after agents, workflows, connectors, etc.) because they reference entities that must exist first.

---

## Directory Structure

Skills live in a `skills/` directory with their own references:

```
skills/<skill-name>/
├── skill.yml              # Skill definition
├── SKILL.md               # Main guide (optional, referenced as skill-guide)
├── references/            # Reference documents
│   ├── events-api.md
│   ├── search.md
│   └── ...
└── schemas/               # Schema files (optional)
    └── ...
```

---

## Naming Conventions

| Element | Convention | Example |
|---------|-----------|---------|
| Skill name | kebab-case, descriptive | `polymarket-sync-events` |
| Skill title | Human-readable with prefix | `"Polymarket - Sync Events"` |
| Reference `name` | `"skill-guide"`, `"skill-reference"`, or `"skill-schema"` | — |
| Reference `reference_id` | kebab-case | `"events-api"`, `"market-types"` |
| Category tags | kebab-case, lowercase | `"data-acquisition"`, `"fine-tuning"` |
| Reference filename | kebab-case `.md` | `references/events-api.md` |
| Skill guide filename | Always `SKILL.md` | `SKILL.md` |

---

## Common Mistakes

| Mistake | Correct |
|---------|---------|
| `skills:` (plural root) | `skill:` (singular object) |
| Missing `domain` | Required — repository URL for provenance |
| Missing `version` | Required — semantic version |
| `metadata.skill` doesn't match skill `name` | Must be identical |
| `skill-reference` without `reference_id` | Required for reference type |
| `skill-guide` with `reference_id` | Not needed for guide type |
| Skills before agents in `_install.yml` | Skills must come **last** in install order |
| `workflows` and `agents` mixed in one entry | Each entry is one or the other |
| Missing `workflow-status` in outputs | Always include for execution tracking |
| `filename` with absolute path | Use relative path from skill directory |
