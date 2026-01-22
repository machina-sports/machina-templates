# Getting Started with Machina Templates

This guide helps you get started creating and using Machina templates.

## What are Machina Templates?

Machina templates are reusable packages containing:
- **Agents** - Orchestrators that execute workflows
- **Workflows** - Task sequences that process data
- **Prompts** - LLM instructions with structured outputs
- **Mappings** - Data transformations
- **Connectors** - External API integrations

## Quick Start

### 1. Install a Template

Use the `/mkn-templates:install-template` skill to install templates:

```bash
/mkn-templates:install-template
```

Or install via MCP:

```python
mcp__docker_localhost__import_templates_from_git(
    repositories=[{
        "repo_url": "https://github.com/machina-sports/machina-templates",
        "template": "agent-templates/chat-completion",
        "repo_branch": "main"
    }]
)
```

### 2. Create a New Template

Use the `/mkn-templates:create-template` skill:

```bash
/mkn-templates:create-template
```

This scaffolds a complete template structure:

```
my-template/
├── _install.yml          # Installation manifest
├── agents/
│   └── executor.yml      # Agent definition
├── workflows/
│   └── main.yml          # Workflow definition
├── prompts/
│   └── reasoning.yml     # Prompt definitions
└── mappings/
    └── transform.yml     # Data transformations
```

### 3. Validate Your Template

Before installing, validate the YAML structure:

```bash
/mkn-templates:validate-template
```

## Template Structure

### Agent YAML

Agents orchestrate workflow execution:

```yaml
agent:
  name: my-agent
  title: My Agent
  description: What this agent does
  context:
    status: "active"
  workflows:
    - name: main-workflow
      inputs:
        message: $.get('messages', [])
      outputs:
        response: $.get('response')
```

### Workflow YAML

Workflows define task sequences:

```yaml
workflow:
  name: main-workflow
  title: Main Workflow
  outputs:
    response: $.get('result')
    workflow-status: "'executed'"
  tasks:
    - type: prompt
      name: generate-response
      connector:
        name: machina-ai
        command: invoke_prompt
        model: gpt-4o
      outputs:
        result: $.get('response')
```

## Available Skills

| Skill | Description |
|-------|-------------|
| `/mkn-templates:create-template` | Scaffold new template |
| `/mkn-templates:validate-template` | Validate YAML structure |
| `/mkn-templates:install-template` | Install via MCP |

## Documentation

- [Template YAML Reference](template-yaml-reference.md) - Complete YAML syntax
- [Connectors Catalog](connectors-catalog.md) - Available connectors

## Examples

Browse the `agent-templates/` directory for working examples:

- `chat-completion` - Basic chat agent
- `machina-assistant` - Full-featured assistant with RAG
- `coverage-tools` - Sports content generation

## ⚠️ CRITICAL: YAML Persistence vs MCP Tools

**Common problem**: Developers use `create_agent()`, `update_workflow()` etc. which work at runtime but **don't persist to git**.

### ❌ WRONG: Using MCP tools to create resources
```python
# Works BUT doesn't persist to git!
mcp__docker_localhost__create_agent(
    name="my-agent",
    workflows=[...]
)
```

### ✅ CORRECT: Edit YAML → Import → Commit
```yaml
# 1. Edit agents/my-agent.yml
agent:
  name: my-agent
  title: My Agent
  workflows:
    - name: main-workflow
```

```python
# 2. Install via MCP
mcp__docker_localhost__get_local_template(
    template="agent-templates/my-template",
    project_path="/app/machina-templates/agent-templates/my-template"
)
```

```bash
# 3. Commit to git
git add agents/my-agent.yml
git commit -m "feat: add my-agent"
```

**Golden rule**: YAML is the source of truth. MCP tools are only for runtime/execution.

## 🧪 Test Driven Development (TDD)

**GOLDEN RULE**: Write the test BEFORE implementing the workflow/agent.

### Visual Summary

```
┌─────────────────────────────────────────────────────────┐
│  ❌ WRONG: Code → Test (or no test)                     │
│  ✅ CORRECT: Test → Code → Commit together              │
└─────────────────────────────────────────────────────────┘

🔴 RED (test)            🟢 GREEN (code)          🔵 REFACTOR
─────────────────────────────────────────────────────────────
testing/                workflows/               workflows/
TESTING-workflow.md     workflow.yml             workflow.yml
                        (minimal impl)           (optimized)
│                       │                        │
│ Scenarios defined     │ Tests PASS ✅          │ Tests PASS ✅
│ Tests FAIL ❌         │                        │
│                       │                        │
└─────────────────────────────────────────────────────────┘
                    git commit -m "feat: add workflow"
```

### Why TDD?

1. ✅ **Defines expected behavior** before coding
2. ✅ **Prevents bugs** and logic errors
3. ✅ **Executable documentation** that never gets outdated
4. ✅ **Facilitates refactoring** - if test passes, change is safe
5. ✅ **LLM executes tests** - automated validation

### TDD Cycle (Red → Green → Refactor)

```
1. 🔴 RED: Write test (will fail because code doesn't exist)
   └─> testing/TESTING-workflow-name.md

2. 🟢 GREEN: Implement minimal workflow/agent to pass
   └─> workflows/workflow-name.yml
   └─> agents/agent-name.yml

3. 🔵 REFACTOR: Improve code while keeping tests passing
   └─> Adjust YAML, add tasks, optimize
```

### Practical Example: Create Translation Workflow

#### 🔴 RED: Write test first

```markdown
# testing/TESTING-translate-text.md

## Scenario 1: Translate English to Portuguese
**Goal**: Translate simple text from EN to PT.

### Execute
```python
mcp__docker_localhost__execute_workflow(
    name="translate-text",
    context={
        "text": "Hello World",
        "target_language": "pt"
    }
)
```

### Expected result
```json
{
  "outputs": {
    "translated_text": "Olá Mundo",  // ✅ Correct translation
    "source_language": "en",
    "workflow-status": "executed"
  }
}
```
```

#### 🟢 GREEN: Implement minimal workflow

```yaml
# workflows/translate-text.yml
workflow:
  name: translate-text
  title: Text Translation
  outputs:
    translated_text: $.get('translation')
    source_language: $.get('detected_language')
    workflow-status: "'executed'"
  tasks:
    - type: prompt
      name: translate
      connector:
        name: machina-ai
        command: invoke_prompt
        model: gpt-4o-mini
      inputs:
        user_prompt: |
          Translate to {{target_language}}: {{text}}
      outputs:
        translation: $.get('response')
```

#### 🟢 GREEN: Test (will pass)

```python
# Execute test
result = mcp__docker_localhost__execute_workflow(
    name="translate-text",
    context={"text": "Hello World", "target_language": "pt"}
)

assert result["outputs"]["translated_text"] == "Olá Mundo"  # ✅ PASSES
```

#### 🔵 REFACTOR: Add language detection

```yaml
# workflows/translate-text.yml (improved)
tasks:
  - type: prompt
    name: detect-language
    connector:
      name: machina-ai
      command: invoke_prompt
      model: gpt-4o-mini
    inputs:
      user_prompt: "Detect language (return 2-letter code): {{text}}"
    outputs:
      detected_language: $.get('response')

  - type: prompt
    name: translate
    connector:
      name: machina-ai
      command: invoke_prompt
      model: gpt-4o-mini
    inputs:
      user_prompt: |
        Translate from {{detected_language}} to {{target_language}}: {{text}}
    outputs:
      translation: $.get('response')
```

#### 🔵 REFACTOR: Re-test (still passes)

```python
# Same test, same validation
result = mcp__docker_localhost__execute_workflow(...)
assert result["outputs"]["translated_text"] == "Olá Mundo"  # ✅ STILL PASSES
assert result["outputs"]["source_language"] == "en"  # ✅ New field also works
```

### Test Document Structure

Test should be **simple markdown** executable by LLM:

```markdown
# Testing: workflow-name

Brief description of what's being tested (1 line).

---

## Prerequisites

1. Template installed in MCP:
```python
mcp__docker_localhost__get_local_template(...)
```

2. Environment variables: `GROQ_API_KEY`, `OPENAI_API_KEY`, etc.

---

## Scenario 1: Scenario Name

**Goal**: What we're validating (1 line).

### Execute workflow

```python
mcp__docker_localhost__execute_workflow(
    name="workflow-name",
    context={
        "param1": "value1"
    }
)
```

### Expected result

```json
{
  "outputs": {
    "field": "expected value",  // ✅ Specific validation
    "workflow-status": "executed"
  }
}
```

### Validation (optional)

```python
# Additional code to validate side effects
mcp__docker_localhost__search_documents(...)
```

---

## Validation Checklist

### ✅ Core Functionality
- [ ] Output X returned correctly
- [ ] Workflow executes without errors
- [ ] Side effect Y occurred

### ✅ Performance
- [ ] TTFT < 1.0s

### ✅ Edge Cases
- [ ] Invalid input returns appropriate error

---

## Troubleshooting

### Error: X
Solution: Y

---

## Cleanup

```python
# Delete test documents
mcp__docker_localhost__bulk_delete_documents(...)
```
```

### Real Examples (Simplified Format)

📁 **Complete guide**: `machina-templates/testing/README.md`

See real test templates:
- `otg-templates/testing/TESTING-pre-routing-reasoning.md` - FAQ/BET classifier (5 scenarios)
- `otg-templates/testing/TESTING-user-load-or-create.md` - Thread creation (3 scenarios)
- `otg-templates/testing/TESTING-misterai-chat-faq-response.md` - FAQ responses with streaming (5 scenarios + batch test)

### Complete TDD Workflow

```bash
# 1. 🔴 RED: Write test FIRST
$ cp machina-templates/testing/TEST-TEMPLATE.md testing/TESTING-my-workflow.md
# Edit template: define scenarios, inputs, expected outputs

# 2. 🟢 GREEN: Implement workflow
$ /mkn-templates:create-template  # Scaffold
# Edit workflows/my-workflow.yml

# 3. Install and test
$ /mkn-templates:install-template
# Execute MCP commands from test document

# 4. 🔵 REFACTOR: Improve while keeping tests passing
# Edit YAML, revalidate with same test

# 5. Commit everything together
$ git add testing/TESTING-my-workflow.md workflows/my-workflow.yml
$ git commit -m "feat: add my-workflow with tests"
```

### Ready-to-Use Test Template

Use the empty template as starting point:

```bash
cp machina-templates/testing/TEST-TEMPLATE.md testing/TESTING-your-workflow.md
```

File: `machina-templates/testing/TEST-TEMPLATE.md`

### When to Create Tests

Create test documents for:
- ✅ **ALWAYS** - Every new workflow/agent
- ✅ External API integrations (connectors)
- ✅ Production-critical features
- ✅ Fixed bugs (regression test)

### Test Locations

```
<template-repo>/testing/
├── TESTING-workflow-name.md
├── TESTING-agent-name.md
└── TESTING-connector-name.md
```

**Examples**:
- `otg-templates/testing/` (private)
- `machina-templates/testing/` (public)
- `docs/testing/` (general platform tests)

## Next Steps

1. Read the [Template YAML Reference](template-yaml-reference.md)
2. Explore existing templates in `agent-templates/`
3. **🔴 Write test document FIRST** (`testing/TESTING-*.md`)
4. **🟢 Create template** with `/mkn-templates:create-template`
5. **🟢 Implement** workflows/agents to pass tests
6. **🔵 Refactor** and validate with existing tests
