---
description: Validate template YAML files against correct patterns before installation
---

# DevOps: Validate Template

Validate Machina template YAML files against correct patterns before installation.

## Trigger

- `/mkn-devops:validate-template`
- "Validate template [path]"
- "Check template YAML"

## Process

### 1. Identify Template Path

Get the template directory path:
```
/Users/fernando/machina/dazn-templates/agent-templates/template-name
```

### 2. Check Required Files

Verify the template has required structure:

```
template-name/
├── _install.yml          # REQUIRED - Installation manifest
├── agents/               # Agent definitions
├── workflows/            # Workflow definitions
├── prompts/              # Prompt definitions
└── ...
```

### 3. Validate _install.yml

Check the installation manifest:

```yaml
# Required fields
setup:
  title: "..."           # Required
  description: "..."     # Required
  value: "..."           # Required - template path
  version: "..."         # Required

datasets:                # Required - at least one dataset
  - type: agent|workflow|prompts|mappings|connector
    path: "..."
```

**Common errors:**
- Missing `setup.title`
- Missing `datasets` array
- Invalid `type` values

### 4. Validate Agent Files

For each agent YAML, check structure:

```yaml
# CORRECT structure
agent:
  name: agent-name           # Required, kebab-case
  title: "..."               # Required
  description: "..."         # Required
  context-agent:             # Input parameters
    param: $.get('param')
  workflows:                 # Required - workflow list
    - name: workflow-name
      inputs: {...}
      outputs: {...}
```

**Common errors:**
- Missing top-level `agent:` key
- Missing `workflows` list
- Wrong expression syntax (using `${var}` instead of `$.get('var')`)

### 5. Validate Workflow Files

For each workflow YAML, check structure:

```yaml
# CORRECT structure
workflow:
  name: workflow-name        # Required, kebab-case
  title: "..."               # Required
  description: "..."         # Required
  inputs:
    param: $.get('param')    # CORRECT format
  outputs:
    result: $.get('result')
  tasks:                     # Required - task list
    - type: document|prompt|mapping|connector
      name: task-name
      ...
```

**Common errors:**
- Missing top-level `workflow:` key
- Wrong inputs format:
  ```yaml
  # WRONG
  inputs:
    param:
      type: string
      required: true

  # CORRECT
  inputs:
    param: $.get('param', 'default')
  ```
- Missing `tasks` array

### 6. Validate Prompt Files

For each prompt YAML, check structure:

```yaml
# CORRECT structure
prompts:
  - type: prompt
    name: prompt-name        # Required
    title: "..."             # Required
    description: "..."
    instruction: |           # Required - LLM instructions
      Your instructions here...
    schema:                  # Required - output schema
      title: SchemaName
      type: object
      required: [field1]
      properties:
        field1:
          type: string
```

**Common errors:**
- Using `prompt:` instead of `prompts:` (array)
- Using `messages:` array instead of `instruction:`
- Missing `schema` definition

### 7. Validate Connector Files

For PyScript connectors:

```yaml
# CORRECT structure
connector:
  name: connector-name
  description: "..."
  filename: connector.py     # Python file
  filetype: pyscript         # NOT "type: pyscript"
  commands:
    - name: "Command Name"
      value: function_name   # Python function
```

**Common errors:**
- Using `type:` instead of `filetype:`
- Using `script:` instead of `filename:`
- Missing `commands` list

### 8. Validate Expression Syntax

Check all expressions use correct syntax:

| Pattern | Status |
|---------|--------|
| `$.get('field')` | ✅ Correct |
| `$.get('field', default)` | ✅ Correct |
| `$.get('a', {}).get('b')` | ✅ Correct |
| `${field}` | ❌ Wrong |
| `$field` | ❌ Wrong |
| `{{field}}` | ❌ Wrong |

### 9. Report Results

Output validation report:

```
Template Validation Report: moderator-assistant
===============================================

_install.yml: ✅ Valid
  - setup.title: "Moderator Assistant"
  - datasets: 15 items

agents/chat-executor.yml: ✅ Valid
  - name: moderator-chat-executor
  - workflows: 12 defined

workflows/chat-reasoning.yml: ✅ Valid
  - tasks: 8 defined
  - inputs: 3 parameters

prompts/chat-reasoning.yml: ✅ Valid
  - prompts: 2 defined

OVERALL: ✅ Template is valid and ready to install
```

Or with errors:

```
Template Validation Report: my-template
=======================================

_install.yml: ✅ Valid

agents/executor.yml: ❌ ERRORS
  Line 5: Missing top-level 'agent:' key
  Line 12: Wrong expression syntax: ${param} → use $.get('param')

workflows/main.yml: ❌ ERRORS
  Line 8: Wrong inputs format - should be 'param: $.get("param")'
  Line 15: Unknown task type 'llm' - use 'prompt'

OVERALL: ❌ 4 errors found. Fix before installing.
```

## Validation Checklist

| Component | Check |
|-----------|-------|
| **_install.yml** | Has `setup` with title, description, value, version |
| **_install.yml** | Has `datasets` array with valid types |
| **Agent** | Has `agent:` top-level key |
| **Agent** | Has `name`, `title`, `workflows` |
| **Workflow** | Has `workflow:` top-level key |
| **Workflow** | Has `name`, `title`, `tasks` |
| **Workflow** | Inputs use `$.get()` syntax |
| **Prompt** | Has `prompts:` array (not `prompt:`) |
| **Prompt** | Each prompt has `instruction` + `schema` |
| **Connector** | Uses `filetype:` (not `type:`) |
| **Connector** | Uses `filename:` (not `script:`) |
| **Expressions** | All use `$.get()` syntax |

## Example Interaction

```
User: Validate my new template at dazn-templates/agent-templates/my-agent

Claude: I'll validate the template structure.

[Reads _install.yml]
✅ _install.yml valid

[Reads agents/executor.yml]
❌ Found issues:
  - Line 10: Using '${thread_id}' - should be "$.get('thread_id')"
  - Line 15: Missing 'outputs' in workflow reference

[Reads workflows/main.yml]
✅ main.yml valid

[Reads prompts/reasoning.yml]
❌ Found issues:
  - Using 'prompt:' instead of 'prompts:' array
  - Missing 'schema' definition

Summary: 2 files need fixes before installation.
See Template YAML Reference guide for correct patterns.
```

## Related

- [Template YAML Reference](../.claude/guides/template-yaml-reference.md) - Complete YAML structure documentation
- [Install Template](./install-template.md) - Install validated templates
