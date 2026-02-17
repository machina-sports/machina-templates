# Setup YAML Schema

Template setup files that define installation metadata and document imports. Covers two related files: `_install.yml` (installation manifest) and `_index.yml` (document import index).

---

## Part 1 — `_install.yml`

The installation manifest defines template metadata and the ordered list of components to install.

**Location**: `agent-templates/<template-name>/_install.yml` or `connectors/<connector-name>/_install.yml`

### Root Structure

```yaml
setup:
  title: <string>            # Required. Display name
  description: <string>      # Required. What this template does
  category: <list>           # Optional. Category tags
  estimatedTime: <string>    # Optional. Install time estimate
  features: <list>           # Optional. Feature list
  integrations: <list>       # Optional. Required connector names
  status: <string>           # Optional. "available" or "draft"
  value: <string>            # Required. Template path
  version: <string>          # Required. Semantic version

datasets: <list>             # Required. Ordered component list
```

### `setup` Fields

#### `title` (required)

```yaml
title: Machina Assistant
title: Google GenAI
title: Sportradar NFL v7
```

#### `description` (required)

```yaml
# Single line
description: Connect to Google GenAI via AI Studio or Vertex AI for AI responses.

# Multiline
description: |
  AI-powered social media content generator that creates engaging memes,
  stats graphics, and interactive quizzes for soccer matchups.
```

#### `category` (optional)

Tags for classification. Array of strings.

```yaml
category:
  - special-templates
  - assistant

category:
  - data-acquisition
  - football
  - football-nfl

category:
  - sports
  - social-media
  - soccer
  - content-creation

category:
  - fan-engagement
```

#### `estimatedTime` (optional)

```yaml
estimatedTime: 1 minute
estimatedTime: 5 minutes
estimatedTime: 10 minutes
estimatedTime: 30 seconds
```

#### `features` (optional)

List of feature descriptions.

```yaml
features:
  - Real-time chat completion (AI Studio & Vertex AI)
  - Real-time image generation (AI Studio)
  - Enterprise-grade Vertex AI integration
```

#### `integrations` (optional)

Required connector names. Tells the installer which connectors must be available.

```yaml
integrations:
  - machina-ai
  - google-genai

integrations:
  - api-football
  - google-genai
  - google-storage
  - machina-ai
```

#### `status` (optional)

```yaml
status: available
status: draft
```

#### `value` (required)

Template path relative to the repository root.

```yaml
# Agent template
value: agent-templates/machina-assistant

# Connector
value: connectors/google-genai
```

#### `version` (required)

Semantic versioning.

```yaml
version: 1.0.0
version: 2.0.0
version: 7.0.0
```

### `datasets` Array

Ordered list of components to install. **Order matters** — dependencies must come first.

```yaml
datasets:
  - type: <string>          # Required. Component type
    path: <string>          # Required. File path relative to template root
```

#### Dataset Types

| Type | Description | File format |
|------|-------------|-------------|
| `agent` | Agent definition | `.yml` |
| `connector` | Connector definition | `.yml` |
| `workflow` | Workflow definition | `.yml` |
| `prompts` | Prompt definitions | `.yml` |
| `prompt` | Single prompt definition | `.yml` |
| `mappings` | Mapping definitions | `.yml` |
| `documents` | Document import index | `_index.yml` |
| `document` | Single document | `.yml` |
| `skill` | Skill registration | `.yml` |

**Note**: Both `prompts` and `prompt` are valid (same for `mappings`/`mapping`). The plural form is more common.

#### Install Order

Always follow this dependency order:

```
1. connectors     → External service definitions
2. documents      → Config files, setup data
3. prompts        → LLM prompt definitions
4. mappings       → Data transformation definitions
5. workflows      → Logic pipelines (depend on prompts, mappings, connectors)
6. agents         → Orchestrators (depend on workflows)
7. skills         → SDK registration (depend on agents, workflows)
```

### Examples

#### Minimal Connector Install

```yaml
datasets:
  - type: connector
    path: openai.yml
  - type: workflow
    path: test-credentials.yml
```

#### Full Agent Template Install

```yaml
datasets:
  # Agent
  - type: agent
    path: agents/assistant-executor.yml

  # Prompts
  - type: prompts
    path: prompts/assistant-reasoning.yml
  - type: prompts
    path: prompts/assistant-response.yml

  # Workflows
  - type: workflow
    path: workflows/assistant-reasoning.yml
  - type: workflow
    path: workflows/assistant-response.yml
  - type: workflow
    path: workflows/assistant-update.yml

  # Configuration
  - type: workflow
    path: _folders.yml
  - type: workflow
    path: _populate-knowledge.yml
```

#### Complex Install with External Connectors

```yaml
datasets:
  # Agent
  - type: agent
    path: agents/roast-agent.yml

  # Prompts
  - type: prompt
    path: prompts/generate-search-queries.yml
  - type: prompt
    path: prompts/generate-search-queries-team-a.yml
  - type: prompt
    path: prompts/generate-roast.yml

  # External connector (relative path)
  - type: connector
    path: "../../connectors/grok/grok.yml"

  # Local connector
  - type: connector
    path: scripts/combine-search-queries.yml

  # Workflows
  - type: workflow
    path: workflows/generate-roast.yml
```

**Relative paths**: Use `../../connectors/<name>/<file>.yml` to reference shared connectors from another location in the repo.

#### Large Connector Install (with agents, mappings, workflows)

```yaml
datasets:
  # Agents
  - type: agent
    path: agents/event-live-update.yml
  - type: agent
    path: agents/event-prelive-update.yml

  # Connectors
  - type: connector
    path: sportradar-nfl.yml
  - type: connector
    path: scripts/detect_season_type.yml

  # Mappings
  - type: mappings
    path: mappings/iptc-sport-event.yml

  # Workflows
  - type: workflow
    path: test-credentials.yml
  - type: workflow
    path: sync-games.yml
  - type: workflow
    path: sync-injuries.yml
  - type: workflow
    path: sync-weekly.yml
```

---

## Part 2 — `_index.yml`

Document import index that maps external files (JSON, Markdown, CSV, etc.) to database documents.

**Location**: `agent-templates/<template-name>/setup/_index.yml` or `<template-name>/knowledge/_index.yml`

### Root Structure

```yaml
documents:
  - name: <string>           # Required. Document name in database
    title: <string>          # Required. Display title
    filename: <string>       # Required. File path relative to _index.yml
    filetype: <string>       # Required. File format
    metadata: <object>       # Optional. Metadata for upsert matching
```

### Field Reference

#### `name` (required)

Document name stored in the database. Used for querying.

```yaml
name: doc-structure
name: setup-engine
name: entity-aliases
```

#### `title` (required)

```yaml
title: Doc Structure
title: Setup Engine
title: Entity Aliases
```

#### `filename` (required)

Path to the file, relative to the `_index.yml` location.

```yaml
filename: folders.json
filename: engine.json
filename: entities.json
```

#### `filetype` (required)

| Value | Description |
|-------|-------------|
| `json` | JSON file — parsed into document value |
| `markdown` | Markdown file — stored as text |
| `text` | Plain text file |
| `html` | HTML file |
| `csv` | CSV file — parsed into rows |
| `jsonl` | JSON Lines — each line is a JSON object |

```yaml
filetype: json
filetype: markdown
```

#### `metadata` (optional)

Key-value pairs for document categorization and upsert matching. When importing, documents are matched by `name` + `metadata` for upsert.

```yaml
metadata:
  category: config
  template: adapters

metadata:
  category: knowledge
  template: adapters

metadata:
  category: instruction
  template: my-template
  instruction_id: main-instructions
```

**Multiple documents with the same `name`**: Differentiated by `metadata` values. The importer uses `name` + `metadata` as the upsert key.

### Example

```yaml
documents:
  - name: doc-structure
    title: Doc Structure
    filename: folders.json
    filetype: json
    metadata:
      category: config
      template: adapters

  - name: setup-engine
    title: Setup Engine
    filename: engine.json
    filetype: json
    metadata:
      category: config
      template: adapters

  - name: site-structure
    title: Site Structure
    filename: structure.json
    filetype: json
    metadata:
      category: config
      template: adapters
```

### How `_index.yml` Is Referenced in `_install.yml`

```yaml
# In _install.yml
datasets:
  - type: documents
    path: setup/_index.yml
```

The installer reads `_index.yml`, finds each referenced file, and imports them as documents.

---

## Common Mistakes

### `_install.yml`

| Mistake | Correct |
|---------|---------|
| Missing `setup.title` | Required field |
| Missing `setup.value` | Required — template path |
| Missing `setup.version` | Required — semantic version |
| Wrong dataset `type` | Must be one of: agent, connector, workflow, prompts, prompt, mappings, documents, document, skill |
| Wrong install order | Connectors first, agents last |
| Absolute paths in `path` | Use relative paths from template root |

### `_index.yml`

| Mistake | Correct |
|---------|---------|
| `document:` (singular root) | `documents:` (array) |
| Missing `filename` | Required — must point to an existing file |
| Missing `filetype` | Required — must be json, markdown, text, html, csv, or jsonl |
| `filetype: md` | `filetype: markdown` |
| `filetype: txt` | `filetype: text` |
| Referenced file doesn't exist | File must exist relative to `_index.yml` location |
| Invalid JSON in `.json` file | Validate JSON syntax before importing |
