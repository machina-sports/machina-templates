# Testing Templates

LLM-executable test documents for validating workflows and agents.

## 🧪 Test Driven Development (TDD)

**ALWAYS** write the test BEFORE implementing the workflow/agent.

### TDD Cycle

```
1. 🔴 RED: Write test (fails because code doesn't exist)
2. 🟢 GREEN: Implement minimal code to pass
3. 🔵 REFACTOR: Improve code while keeping tests passing
```

## Quick Start

### 1. Copy the template

```bash
cp TEST-TEMPLATE.md TESTING-your-workflow.md
```

### 2. Define scenarios

Edit the file and define:
- **Prerequisites**: Installed template, environment variables
- **Scenarios**: Expected inputs and outputs for each case
- **Validations**: Test checklist
- **Troubleshooting**: Common errors

### 3. Implement the workflow

```bash
/mkn-templates:create-template  # Scaffold
# Edit workflows/your-workflow.yml
```

### 4. Execute tests

Copy and paste MCP commands from test document directly into LLM.

## Test Structure

```markdown
# Testing: workflow-name

## Prerequisites
1. Template installed
2. Environment variables

## Scenario 1: Name
**Goal**: What to validate

### Execute
```python
mcp__docker_localhost__execute_workflow(...)
```

### Expected result
```json
{
  "outputs": {
    "field": "value"  // ✅ Validation
  }
}
```

## Validation Checklist
- [ ] Test 1
- [ ] Test 2

## Troubleshooting
### Error X
Solution Y

## Cleanup
```python
mcp__docker_localhost__bulk_delete_documents(...)
```
```

## Real Examples

**Simplified format** (recommended format):
- `otg-templates/testing/TESTING-pre-routing-reasoning.md` - FAQ/BET classifier
- `otg-templates/testing/TESTING-user-load-or-create.md` - Thread creation
- `otg-templates/testing/TESTING-misterai-chat-faq-response.md` - FAQ responses with streaming

**Complete format** (for complex cases):
- `docs/testing/TESTING-pre-routing-reasoning.md` - Same workflow, more detailed

## When to Create Tests

✅ **ALWAYS**:
- Every new workflow
- Every new agent
- External API integrations (connectors)
- Critical features
- Fixed bugs (regression test)

## Benefits

1. ✅ **Defines behavior** before coding
2. ✅ **Prevents bugs** - test fails if code breaks
3. ✅ **Executable documentation** - never gets outdated
4. ✅ **Facilitates refactoring** - if test passes, change is safe
5. ✅ **LLM executes** - automated validation

## Test Locations

```
<repo>/testing/
├── TEST-TEMPLATE.md          # Empty template
├── TESTING-workflow-1.md
├── TESTING-workflow-2.md
└── TESTING-agent-name.md
```

**Examples**:
- `machina-templates/testing/` (public)
- `otg-templates/testing/` (private)
- `docs/testing/` (general platform tests)

---

**Remember**: 🔴 Test FIRST → 🟢 Implement → 🔵 Refactor
