# Validate

Validate template YAML files against correct patterns before installation.

## Executable Repository Validator

For this skill package and both generated compatibility aliases, run from the
repository root:

```bash
python3 scripts/validate-machina-agent-builder.py
```

The command checks YAML parsing and identities, dataset paths and ordering,
registered references, local Markdown links, canonical/legacy parity, provider
examples, and discovery triggers. Its errors include the affected path and a
remediation hint. Use the manual checks below for template-specific semantic
review that cannot be proven from package structure alone.

## Trigger

- "Validate template", "Check template YAML"

## Process

### 1. Identify Template Path

Get the template directory path from the user.

### 2. Check Directory Structure

```
template-name/
├── _install.yml          # Required
├── agents/               # Agent definitions
├── workflows/            # Workflow definitions
├── prompts/              # Prompt definitions
└── ...
```

### 3. Validate Each Component

For each file type, read the corresponding schema and check:

| Component | Schema | Key Checks |
|-----------|--------|------------|
| `_install.yml` | [setup.md](../schemas/setup.md) Part 1 | Has `setup` with title/description/value/version; has `datasets` array with valid types; correct install order |
| `_index.yml` | [setup.md](../schemas/setup.md) Part 2 | Has `documents:` array; each entry has name/title/filename/filetype; referenced files exist; valid filetype values |
| Agent `.yml` | [agent.md](../schemas/agent.md) | Has `agent:` root key; has name/title/workflows; expressions use `$.get()` |
| Workflow `.yml` | [workflow.md](../schemas/workflow.md) | Has `workflow:` root key; has name/title/tasks; inputs/outputs use `$.get()` |
| Prompt `.yml` | [prompt.md](../schemas/prompt.md) | Uses `prompts:` array (not `prompt:`); each has `instruction` + `schema`; schema has `type: object` |
| Mapping `.yml` | [mapping.md](../schemas/mapping.md) | Uses `mappings:` array; each has `type: mapping` + `outputs` |
| Connector `.yml` | [connector.md](../schemas/connector.md) | Uses `filetype:` (not `type:`); uses `filename:` (not `script:`); has `commands` for pyscript |
| `skill.yml` | [skill.md](../schemas/skill.md) | Has `skill:` root key; has name/title/status/domain/version; reference files exist |

### 4. Validate Expressions

| Pattern | Status |
|---------|--------|
| `$.get('field')` | Correct |
| `$.get('field', default)` | Correct |
| `$.get('a', {}).get('b')` | Correct |
| `${field}` | Wrong |
| `$field` | Wrong |
| `{{field}}` | Wrong (only valid inside prompt `instruction:` text) |

### 5. Validate Cross-References

- Every `workflows[].name` in agent files → matches a workflow `name`
- Every prompt task `name` in workflows → matches a prompt `name`
- Every mapping task `name` in workflows → matches a mapping `name`
- Every `datasets[].path` in `_install.yml` → file exists
- Every connector in `context-variables` → has credentials configured

### 6. Report Results

```
Template Validation Report: template-name
==========================================

_install.yml: ✅ Valid
  - setup.title: "Template Name"
  - datasets: 15 items

agents/executor.yml: ✅ Valid
  - name: template-name-executor
  - workflows: 12 defined

workflows/main.yml: ❌ ERRORS
  Line 8: Wrong inputs format - use $.get('param')
  Line 15: Unknown task type 'llm' - use 'prompt'

OVERALL: ❌ 2 errors found. Fix before installing.
```

## Validation Checklist

| Component | Check |
|-----------|-------|
| **_install.yml** | Has `setup` with title, description, value, version |
| **_install.yml** | Has `datasets` array with valid types |
| **_install.yml** | Install order: connectors → documents → prompts → mappings → workflows → agents → skills |
| **Agent** | Has `agent:` root key, `name`, `title`, `workflows` |
| **Workflow** | Has `workflow:` root key, `name`, `title`, `tasks` |
| **Workflow** | Inputs/outputs use `$.get()` syntax |
| **Prompt** | Uses `prompts:` array (not `prompt:`) with `instruction:` (singular) |
| **Prompt** | Each prompt has `instruction` + `schema` with `type: object` |
| **Mapping** | Uses `mappings:` array, each has `type: mapping` + `outputs` |
| **Connector** | Uses `filetype:` (not `type:`) and `filename:` (not `script:`) |
| **Connector** | Has `commands` for pyscript type |
| **_index.yml** | Has `documents:` array, all referenced files exist |
| **_index.yml** | `filetype` is one of: json, markdown, text, html, csv, jsonl |
| **skill.yml** | Has `skill:` root with name/title/status/domain/version |
| **Expressions** | All use `$.get()` syntax |

## Related

- [Create](./create.md) — Scaffold YAML components
- [Install](./install.md) — Deploy validated templates
- **Schemas**: [agent](../schemas/agent.md) · [workflow](../schemas/workflow.md) · [prompt](../schemas/prompt.md) · [connector](../schemas/connector.md) · [mapping](../schemas/mapping.md) · [setup](../schemas/setup.md) · [skill](../schemas/skill.md)
