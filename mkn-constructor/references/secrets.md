# Secrets

Configure secrets in the Machina vault for use with connectors in workflows.

## Trigger

- "Configure secrets for a connector", "Add API key to vault"

## Key Concepts

### Naming Convention

Secrets MUST follow the `TEMP_CONTEXT_VARIABLE_*` pattern:

```
TEMP_CONTEXT_VARIABLE_{SERVICE}_{FIELD}
```

Examples:
- `TEMP_CONTEXT_VARIABLE_GOOGLE_STORAGE_API_KEY`
- `TEMP_CONTEXT_VARIABLE_OPENAI_API_KEY`
- `TEMP_CONTEXT_VARIABLE_SPORTRADAR_API_KEY`

### How Secrets Flow

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Vault Secret  │ --> │ context-variables│ --> │ Connector inputs│
│                 │     │   in workflow    │     │                 │
│ name: TEMP_...  │     │ $TEMP_...        │     │ $.get('field')  │
│ key: "value"    │     │                  │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

## Step-by-Step Process

### 1. Create Secrets in Vault

Create ONE secret at a time:

```python
mcp__docker-localhost__create_secrets({
  "name": "TEMP_CONTEXT_VARIABLE_GOOGLE_STORAGE_BUCKET_NAME",
  "key": "machina-templates-bucket-default"
})

mcp__docker-localhost__create_secrets({
  "name": "TEMP_CONTEXT_VARIABLE_GOOGLE_STORAGE_API_KEY",
  "key": '{"type":"service_account","project_id":"...",...}'
})
```

### 2. Verify Secrets Exist

```python
mcp__docker-localhost__check_secrets(name="TEMP_CONTEXT_VARIABLE_GOOGLE_STORAGE_API_KEY")
# Returns: {"status": "success", "message": "Secret ... exists."}
```

### 3. Configure Workflow

Add `context-variables` section to workflow YAML (see [workflow.md](../schemas/workflow.md) for full context-variables reference):

```yaml
workflow:
  name: my-workflow
  context-variables:
    google-storage:
      api_key: $TEMP_CONTEXT_VARIABLE_GOOGLE_STORAGE_API_KEY
      bucket_name: $TEMP_CONTEXT_VARIABLE_GOOGLE_STORAGE_BUCKET_NAME
```

The `$` prefix tells the SDK to look up the secret by name from vault.

### 4. Pass Credentials to Connector

In connector tasks, pass credentials via inputs:

```yaml
- type: connector
  name: upload-to-gcs
  connector:
    name: google-storage
    command: invoke_upload
  inputs:
    api_key: "$.get('api_key')"
    bucket_name: "$.get('bucket_name')"
```

## Common Mistakes

| Mistake | Correct |
|---------|---------|
| `$.secrets.google-storage.api_key` | Use `context-variables` + `$.get()` |
| Non-standard name (`google-storage-key`) | Must be `TEMP_CONTEXT_VARIABLE_*` |
| Multiple fields in one `create_secrets` call | Create one secret at a time |
| Missing `context-variables` in workflow | Required — secrets won't resolve without it |

## Reference: Known Credential Patterns

```yaml
context-variables:
  google-genai:
    credential: $TEMP_CONTEXT_VARIABLE_VERTEX_AI_CREDENTIAL
    project_id: $TEMP_CONTEXT_VARIABLE_VERTEX_AI_PROJECT_ID
    api_key: $TEMP_CONTEXT_VARIABLE_GOOGLE_GENERATIVE_AI_API_KEY
  google-storage:
    api_key: $TEMP_CONTEXT_VARIABLE_GOOGLE_STORAGE_API_KEY
    bucket_name: $TEMP_CONTEXT_VARIABLE_GOOGLE_STORAGE_BUCKET_NAME
  machina-ai:
    api_key: $TEMP_CONTEXT_VARIABLE_SDK_OPENAI_API_KEY
```

## MCP Commands

```python
# Create
mcp__docker-localhost__create_secrets({"name": "TEMP_...", "key": "value"})

# Check
mcp__docker-localhost__check_secrets(name="TEMP_...")

# Delete
mcp__docker-localhost__delete_secrets(name="TEMP_...")
```

## Troubleshooting

### "API key is required" Error
1. Check secret exists: `check_secrets(name="TEMP_...")`
2. Verify workflow has `context-variables` section
3. Ensure connector inputs pass `$.get('api_key')`
4. Confirm secret name follows `TEMP_CONTEXT_VARIABLE_*` pattern

### Secret Creation Fails with 500 Error
- Create secrets one at a time
- For JSON values, ensure proper escaping
- Check value length and character validity

## Related

- [Install](./install.md) — Install templates (requires secrets)
- [Analyze](./analyze.md) — Discover required credentials
