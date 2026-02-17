# Create

Scaffold individual Machina YAML components with correct structure.

## Trigger

- `/mkn-templates:create-template`
- "Create new template", "Scaffold agent template"

## Process

### 1. Gather Requirements

Ask user for:
- **Template name**: kebab-case (e.g., `sports-predictions`)
- **Template type**: `agent-template` or `connector`
- **Target repo**: the repository where this template will live
- **Components needed**: agents, workflows, prompts, mappings, connectors

### 2. Create Directory Structure

```bash
# Agent template
mkdir -p agent-templates/{name}/{agents,workflows,prompts,mappings,scripts,documents}

# Connector
mkdir -p connectors/{name}
```

### 3. Generate Files

Read the relevant schema before generating each component:

| Component | Schema | Output |
|-----------|--------|--------|
| Install manifest | [setup.md](../schemas/setup.md) Part 1 | `_install.yml` |
| Document index | [setup.md](../schemas/setup.md) Part 2 | `setup/_index.yml` |
| Agent | [agent.md](../schemas/agent.md) | `agents/{name}-executor.yml` |
| Workflow | [workflow.md](../schemas/workflow.md) | `workflows/{name}-main.yml` |
| Prompt | [prompt.md](../schemas/prompt.md) | `prompts/{name}-prompts.yml` |
| Mapping | [mapping.md](../schemas/mapping.md) | `mappings/{name}-transform.yml` |
| Connector | [connector.md](../schemas/connector.md) | `scripts/{name}-processor.yml` |
| Skill | [skill.md](../schemas/skill.md) | `skill.yml` |

**Install order in `_install.yml`**: connectors → documents → prompts → mappings → workflows → agents → skills.

### 4. Cross-Entity Wiring

After generating individual files, verify these connections:

- **Agent → Workflows**: Each `workflows[].name` in the agent must match a `workflow.name` in a workflow file.
- **Workflow → Prompts**: Each prompt task `name` must match a `prompts[].name` in a prompt file.
- **Workflow → Connectors**: `context-variables` must declare credentials for every connector used in tasks.
- **Workflow → Mappings**: Each mapping task `name` must match a `mappings[].name` in a mapping file.
- **`_install.yml` → Files**: Every `datasets[].path` must point to an existing file.

## Template Type Patterns

### Chat Agent (Conversation)
- Thread management via `context-agent.thread_id` and `context-agent.messages`
- Typical flow: reasoning → main → response workflows

### One-Shot Agent (No Thread)
- Auto-creates thread if needed, no conversation state

### Periodic Agent (Scheduled)
- `config-frequency` in `context` for scheduling
- Idempotency checks, batch processing
- Reference: `machina-templates/agent-templates/power-ranking-periodic`

### Connector Only
- PyScript or REST API, reusable across templates
- Reference: `machina-templates/connectors/google-genai`

## Differences from `init`

| Aspect | `create` | `init` |
|--------|----------|--------|
| **Focus** | YAML file content | Full project scaffold with docs |
| **Creates** | Individual YAML components | Everything + `_folders.yml`, `_setup.yml`, README, CHANGES |
| **When to use** | Adding components to existing template | Starting a new template from scratch |

## Related

- [Init](./init.md) — Full project scaffold with boilerplate
- [Validate](./validate.md) — Validate YAML before installing
- [Install](./install.md) — Deploy templates
- **Schemas**: [agent](../schemas/agent.md) · [workflow](../schemas/workflow.md) · [prompt](../schemas/prompt.md) · [connector](../schemas/connector.md) · [mapping](../schemas/mapping.md) · [setup](../schemas/setup.md) · [skill](../schemas/skill.md)
