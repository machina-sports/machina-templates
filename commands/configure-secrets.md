---
description: Configure secrets in the Machina vault for use in workflows and connectors
---

# Configure Secrets

This skill documents how to properly configure secrets in the Machina SDK vault for use with connectors in workflows.

## Trigger

User says:
- `/mkn-devops:configure-secrets`
- "How do I configure secrets for a connector?"
- "Setup credentials for google-storage"
- "Add API key to vault"

## Key Concepts

### Secret Naming Convention

Secrets MUST follow the `TEMP_CONTEXT_VARIABLE_*` naming pattern:

```
TEMP_CONTEXT_VARIABLE_{SERVICE}_{FIELD}
```

**Examples:**
- `TEMP_CONTEXT_VARIABLE_GOOGLE_STORAGE_API_KEY`
- `TEMP_CONTEXT_VARIABLE_GOOGLE_STORAGE_BUCKET_NAME`
- `TEMP_CONTEXT_VARIABLE_OPENAI_API_KEY`
- `TEMP_CONTEXT_VARIABLE_SPORTRADAR_API_KEY`

### Secret Structure

Each secret has two fields:
- `name`: The secret identifier (TEMP_CONTEXT_VARIABLE_* format)
- `key`: The actual secret value (string)

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

### 1. Create Secrets in Vault via MCP

Create ONE secret at a time using MCP:

```python
# Create bucket name secret
mcp__docker-localhost__create_secrets({
  "name": "TEMP_CONTEXT_VARIABLE_GOOGLE_STORAGE_BUCKET_NAME",
  "key": "machina-templates-bucket-default"
})

# Create API key secret (JSON service account)
mcp__docker-localhost__create_secrets({
  "name": "TEMP_CONTEXT_VARIABLE_GOOGLE_STORAGE_API_KEY",
  "key": '{"type":"service_account","project_id":"...",...}'
})
```

**IMPORTANT:** Create secrets one at a time. The API may fail with complex JSON if multiple fields are passed together.

### 2. Verify Secrets Exist

```python
mcp__docker-localhost__check_secrets(name="TEMP_CONTEXT_VARIABLE_GOOGLE_STORAGE_API_KEY")
# Returns: {"status": "success", "message": "Secret ... exists."}
```

### 3. Configure Workflow with context-variables

Add `context-variables` section to workflow YAML:

```yaml
workflow:
  name: my-workflow
  context-variables:
    google-storage:
      api_key: $TEMP_CONTEXT_VARIABLE_GOOGLE_STORAGE_API_KEY
      bucket_name: $TEMP_CONTEXT_VARIABLE_GOOGLE_STORAGE_BUCKET_NAME
  inputs:
    # ... workflow inputs
  tasks:
    # ... workflow tasks
```

**Key points:**
- The `$` prefix tells SDK to look up the secret
- SDK strips `$` and fetches secret by name from vault
- Values become available via `$.get('field_name')`

### 4. Pass Credentials to Connector

In the connector task, pass credentials via inputs:

```yaml
- type: connector
  name: upload-to-gcs
  connector:
    name: google-storage
    command: invoke_upload
  inputs:
    api_key: "$.get('api_key')"
    bucket_name: "$.get('bucket_name')"
    file_path: "$.get('temp_path')"
    # ... other inputs
```

## Complete Example: Google Storage

### 1. Create Secrets

```python
# Secret 1: Bucket name
mcp__docker-localhost__create_secrets({
  "name": "TEMP_CONTEXT_VARIABLE_GOOGLE_STORAGE_BUCKET_NAME",
  "key": "machina-templates-bucket-default"
})

# Secret 2: Service account JSON
mcp__docker-localhost__create_secrets({
  "name": "TEMP_CONTEXT_VARIABLE_GOOGLE_STORAGE_API_KEY",
  "key": '{"type":"service_account","project_id":"my-project",...}'
})
```

### 2. Workflow Configuration

```yaml
workflow:
  name: upload-file-to-gcs
  context-variables:
    google-storage:
      api_key: $TEMP_CONTEXT_VARIABLE_GOOGLE_STORAGE_API_KEY
      bucket_name: $TEMP_CONTEXT_VARIABLE_GOOGLE_STORAGE_BUCKET_NAME
  inputs:
    file_path: "$.get('file_path')"
  tasks:
    - type: connector
      name: upload-file
      connector:
        name: google-storage
        command: invoke_upload
      inputs:
        api_key: "$.get('api_key')"
        bucket_name: "$.get('bucket_name')"
        file_path: "$.get('file_path')"
      outputs:
        url: "$.get('url', '')"
```

## Common Mistakes to Avoid

### Wrong: Using `$.secrets.*` syntax in connector headers

```yaml
# DOES NOT WORK - $.secrets syntax is not supported
headers:
  api_key: "$.secrets.google-storage.api_key"
```

### Wrong: Creating secrets with non-standard names

```python
# DOES NOT WORK - Name doesn't follow TEMP_CONTEXT_VARIABLE pattern
mcp__docker-localhost__create_secrets({
  "name": "google-storage-api-key",
  "key": "..."
})
```

### Wrong: Passing multiple fields in one secret creation

```python
# MAY FAIL - API has issues with complex nested data
mcp__docker-localhost__create_secrets({
  "name": "google-storage",
  "api_key": "...",
  "bucket_name": "..."
})
```

### Wrong: Missing context-variables in workflow

```yaml
# DOES NOT WORK - Secrets won't be resolved
workflow:
  name: my-workflow
  # Missing context-variables section!
  tasks:
    - type: connector
      inputs:
        api_key: "$.get('api_key')"  # Will be None!
```

## Reference: Existing Implementations

### personalized-podcast (machina-templates)

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

### dazn-runofshow (dazn-templates)

```yaml
context-variables:
  google-storage:
    api_key: $TEMP_CONTEXT_VARIABLE_GOOGLE_STORAGE_API_KEY
    bucket_name: $TEMP_CONTEXT_VARIABLE_GOOGLE_STORAGE_BUCKET_NAME
```

## MCP Commands Reference

### Create Secret

```python
mcp__docker-localhost__create_secrets({
  "name": "TEMP_CONTEXT_VARIABLE_SERVICE_FIELD",
  "key": "secret-value"
})
```

### Check Secret Exists

```python
mcp__docker-localhost__check_secrets(name="TEMP_CONTEXT_VARIABLE_SERVICE_FIELD")
```

### Delete Secret

```python
mcp__docker-localhost__delete_secrets(name="TEMP_CONTEXT_VARIABLE_SERVICE_FIELD")
```

## Troubleshooting

### "API key is required" Error

1. Check secret exists: `check_secrets(name="TEMP_CONTEXT_VARIABLE_...")`
2. Verify workflow has `context-variables` section
3. Ensure connector inputs pass `$.get('api_key')`
4. Confirm secret name follows `TEMP_CONTEXT_VARIABLE_*` pattern

### Secret Creation Fails with 500 Error

- Create secrets one at a time
- For JSON values (like service accounts), ensure proper escaping
- Check the key value isn't too long or contains invalid characters

### Connector Headers Not Resolving

- The `$.secrets.*` syntax does NOT work
- Use `context-variables` + `$.get()` pattern instead
- Remove any `headers` configuration from connector in database

## Technical Details

### How SDK Resolves Secrets

Location: `core/workflow/context.py`

```python
# Line 820-823
if val.startswith("$"):
    secret_value = get_integration_secret(val[1:])  # Strips $ prefix
    task_context["headers"][key] = secret_value
    self.set_item(key, secret_value)
```

### Vault Repository

Location: `core/vault/repository.py`

```python
def get_secret_by_name(name: str):
    collection = MongoDBConnection().get_collection("vault")
    result = collection.find_one({ "name": name })
    # Decrypts and returns credentials
```

## Success Criteria

- Secrets created with `TEMP_CONTEXT_VARIABLE_*` naming
- Workflow has `context-variables` section
- Connector inputs use `$.get('field')` pattern
- Workflow executes without "API key is required" error
