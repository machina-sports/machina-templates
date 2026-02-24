# Google Workstation Connector

Manage Google Cloud Workstations lifecycle and execute Claude Code sessions remotely using the `google-cloud-workstations` SDK.

## Requirements

- **GCP Service Account** with `roles/workstations.admin` (or equivalent permissions)
- **google-cloud-workstations** Python package (included in `requirements.txt`)

## IAM Roles

| Role | Purpose |
|------|---------|
| `roles/workstations.admin` | Full lifecycle management (create, start, stop, delete) |
| `roles/workstations.user` | Start/stop and generate access tokens (no create/delete) |
| `roles/workstations.viewer` | List and get operations only |

## Credential Format

The `credential` parameter accepts a GCP service account JSON key (string or dict):

```json
{
  "type": "service_account",
  "project_id": "my-project",
  "private_key_id": "...",
  "private_key": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n",
  "client_email": "sa@my-project.iam.gserviceaccount.com",
  "client_id": "...",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token"
}
```

## Commands

| Command | Description | Required Params |
|---------|-------------|-----------------|
| `invoke_create_workstation` | Create a new workstation | + workstation_id |
| `invoke_delete_workstation` | Delete a workstation | + workstation |
| `invoke_execute_claude` | Run Claude Code headless | + workstation, prompt |
| `invoke_generate_access_token` | Get short-lived access token | + workstation |
| `invoke_get_workstation` | Get workstation details/state | + workstation |
| `invoke_kill_session` | Kill a Claude session by session_id or pid | + workstation, session_id or pid |
| `invoke_list_clusters` | List clusters in a location | credential, project_id |
| `invoke_list_configs` | List configs in a cluster | + cluster |
| `invoke_list_sessions` | List active Claude sessions on a workstation | + workstation |
| `invoke_list_workstations` | List workstations in a config | + config |
| `invoke_send_message` | Send a prompt to Claude with real-time streaming | + workstation, prompt |
| `invoke_start_workstation` | Start a stopped workstation | + workstation |
| `invoke_stop_workstation` | Stop a running workstation | + workstation |
| `invoke_stream_update` | Publish a stream update to Redis pub/sub | document_id |

All commands accept optional `location` (default: `us-central1`).

LRO commands (`create`, `start`, `stop`, `delete`) accept optional `wait` (default: `true`). Set to `false` to return the operation ID immediately.

## Usage Examples

### List clusters

```python
mcp__docker-localhost__connector_executor(
    item_id="<connector_id>",
    data={
        "connector_exec": "invoke_list_clusters",
        "credential": "<service_account_json>",
        "project_id": "my-project",
        "location": "us-central1"
    }
)
```

### Create and start a workstation

```python
# Create
mcp__docker-localhost__connector_executor(
    item_id="<connector_id>",
    data={
        "connector_exec": "invoke_create_workstation",
        "credential": "<service_account_json>",
        "project_id": "my-project",
        "cluster": "my-cluster",
        "config": "my-config",
        "workstation_id": "dev-ws-01",
        "display_name": "Dev Workstation 01"
    }
)

# Start
mcp__docker-localhost__connector_executor(
    item_id="<connector_id>",
    data={
        "connector_exec": "invoke_start_workstation",
        "credential": "<service_account_json>",
        "project_id": "my-project",
        "cluster": "my-cluster",
        "config": "my-config",
        "workstation": "dev-ws-01"
    }
)
```

### Execute Claude Code remotely

```python
mcp__docker-localhost__connector_executor(
    item_id="<connector_id>",
    data={
        "connector_exec": "invoke_execute_claude",
        "credential": "<service_account_json>",
        "project_id": "my-project",
        "cluster": "my-cluster",
        "config": "my-config",
        "workstation": "dev-ws-01",
        "prompt": "Analyze the project structure and summarize the architecture.",
        "output_format": "json",
        "timeout": 300
    }
)
```

## Installation

```python
mcp__docker-localhost__import_template_from_local(
    template="connectors/google-workstation",
    project_path="/app/machina-templates/connectors/google-workstation"
)
```
